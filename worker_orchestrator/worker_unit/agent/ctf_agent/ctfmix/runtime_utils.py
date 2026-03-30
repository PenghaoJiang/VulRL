"""Small runtime helpers copied and simplified from enigma-plus."""

from __future__ import annotations

import os
import random
import re
import select
import shlex
import socket
import subprocess
import tarfile
import tempfile
import time
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any

import docker
from docker.models.containers import Container

from .log import get_logger

logger = get_logger("ctfmix.runtime_utils")

DOCKER_START_UP_DELAY = float(os.environ.get("SWE_AGENT_DOCKER_START_UP_DELAY", "1"))
DOCKER_COMPOSE_STARTUP_DELAY = float(os.environ.get("SWE_AGENT_DOCKER_START_UP_DELAY", "1200"))
DEFAULT_PORT_RANGE_START = 10000
DEFAULT_PORT_RANGE_END = 20000
PROCESS_DONE_MARKER_START = "///PROCESS-DONE:"
PROCESS_DONE_MARKER_END = ":PROCESS-DONE///"
PROCESS_DONE_REGEX = re.compile(rf"{PROCESS_DONE_MARKER_START}(.+?){PROCESS_DONE_MARKER_END}")


class NoOutputTimeoutError(TimeoutError):
    """Raised when a command produces no output for too long."""


def is_port_in_use(port: int, host: str = "localhost") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def get_multiple_available_ports(
    count: int,
    start_port: int = DEFAULT_PORT_RANGE_START,
    end_port: int = DEFAULT_PORT_RANGE_END,
    host: str = "localhost",
) -> list[int]:
    if count <= 0:
        return []

    port_range = list(range(start_port, end_port + 1))
    random.shuffle(port_range)

    allocated_ports: list[int] = []
    temp_sockets: list[socket.socket] = []

    try:
        for port in port_range:
            if len(allocated_ports) >= count:
                break
            if is_port_in_use(port, host):
                continue
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind((host, port))
                sock.listen(1)
                temp_sockets.append(sock)
                allocated_ports.append(port)
            except OSError:
                continue

        if len(allocated_ports) < count:
            raise RuntimeError(
                f"Could only find {len(allocated_ports)} available ports out of {count} "
                f"requested in range {start_port}-{end_port}"
            )
        return allocated_ports
    finally:
        for sock in temp_sockets:
            try:
                sock.close()
            except Exception:
                pass


def create_dynamic_docker_compose(
    original_compose_path: Path,
    container_name_suffix: str,
    dynamic_network_name: str,
    port_mappings: dict[str, int],
) -> Path:
    import yaml

    logger.info("Creating external network: %s", dynamic_network_name)
    ensure_docker_network(dynamic_network_name)

    compose_data = yaml.safe_load(original_compose_path.read_text()) or {}
    if not compose_data:
        raise ValueError("Empty or invalid docker-compose.yml file")

    original_networks = compose_data.get("networks") or {}
    network_name_mapping: dict[str, str] = {}
    rewritten_networks: dict[str, Any] = {}
    for network_name, network_config in original_networks.items():
        if network_name == "ctfnet":
            network_name_mapping[network_name] = dynamic_network_name
            rewritten_networks[dynamic_network_name] = {
                "name": dynamic_network_name,
                "external": True,
                "driver": "bridge",
            }
            continue

        rewritten_name = f"{network_name}-{container_name_suffix}"
        network_name_mapping[network_name] = rewritten_name
        rewritten_config = dict(network_config) if isinstance(network_config, dict) else network_config
        if isinstance(rewritten_config, dict):
            rewritten_config["name"] = rewritten_name
            rewritten_config.pop("external", None)
        rewritten_networks[rewritten_name] = rewritten_config

    if dynamic_network_name not in rewritten_networks:
        rewritten_networks[dynamic_network_name] = {
            "name": dynamic_network_name,
            "external": True,
            "driver": "bridge",
        }
    if "ctfnet" not in network_name_mapping:
        network_name_mapping["ctfnet"] = dynamic_network_name

    if "services" in compose_data:
        new_services: dict[str, Any] = {}
        service_name_mapping: dict[str, str] = {}

        for service_name, service_config in compose_data["services"].items():
            service_copy = dict(service_config)
            new_service_name = f"{service_name}-{container_name_suffix}"
            service_name_mapping[service_name] = new_service_name

            if "container_name" in service_copy:
                original_name = service_copy["container_name"]
                service_copy["container_name"] = f"{original_name}-{container_name_suffix}"
            else:
                service_copy["container_name"] = new_service_name

            if "ports" in service_copy and port_mappings:
                updated_ports = []
                for port_config in service_copy["ports"]:
                    if isinstance(port_config, str) and ":" in port_config:
                        external_port, internal_port = port_config.split(":", 1)
                        mapping_key = f"{service_name}:{internal_port}"
                        if mapping_key in port_mappings:
                            updated_ports.append(f"{port_mappings[mapping_key]}:{internal_port}")
                        elif internal_port in port_mappings:
                            updated_ports.append(f"{port_mappings[internal_port]}:{internal_port}")
                        else:
                            updated_ports.append(port_config)
                    elif isinstance(port_config, int):
                        internal_port = str(port_config)
                        mapping_key = f"{service_name}:{internal_port}"
                        if mapping_key in port_mappings:
                            updated_ports.append(f"{port_mappings[mapping_key]}:{internal_port}")
                        elif internal_port in port_mappings:
                            updated_ports.append(f"{port_mappings[internal_port]}:{internal_port}")
                        else:
                            updated_ports.append(port_config)
                    else:
                        updated_ports.append(port_config)
                service_copy["ports"] = updated_ports

            if "depends_on" in service_copy:
                depends_on = service_copy["depends_on"]
                if isinstance(depends_on, list):
                    service_copy["depends_on"] = [service_name_mapping.get(dep, dep) for dep in depends_on]
                elif isinstance(depends_on, dict):
                    service_copy["depends_on"] = {
                        service_name_mapping.get(dep, dep): config for dep, config in depends_on.items()
                    }

            if "network_mode" in service_copy:
                del service_copy["network_mode"]

            service_networks = service_copy.get("networks")
            if service_networks is None:
                service_copy["networks"] = [dynamic_network_name]
            elif isinstance(service_networks, list):
                service_copy["networks"] = [network_name_mapping.get(net, net) for net in service_networks]
            elif isinstance(service_networks, dict):
                rewritten_service_networks = {}
                for net_name, net_config in service_networks.items():
                    rewritten_service_networks[network_name_mapping.get(net_name, net_name)] = net_config
                service_copy["networks"] = rewritten_service_networks

            new_services[new_service_name] = service_copy

        compose_data["services"] = new_services

    compose_data["networks"] = rewritten_networks

    temp_file_path = original_compose_path.parent / f"docker-compose-{uuid.uuid4().hex[:8]}.yml"
    temp_file_path.write_text(yaml.safe_dump(compose_data, sort_keys=False))
    return temp_file_path


def get_docker_compose(
    docker_compose_path: Path,
    container_name_suffix: str | None = None,
    dynamic_ports: bool = False,
    challenge_internal_port: int | None = None,
) -> tuple[Path, dict[str, int], str]:
    actual_compose_path = docker_compose_path
    port_mappings: dict[str, int] = {}

    if dynamic_ports and container_name_suffix:
        dynamic_network_name = f"ctfnet-{container_name_suffix}"
        try:
            import yaml

            compose_data = yaml.safe_load(docker_compose_path.read_text()) or {}
            port_mappings_needed: list[tuple[str, str, str]] = []

            for service_name, service_config in (compose_data.get("services") or {}).items():
                if not isinstance(service_config, dict):
                    continue
                for port_mapping in service_config.get("ports", []):
                    if isinstance(port_mapping, str) and ":" in port_mapping:
                        external_port, internal_port = port_mapping.split(":", 1)
                        port_mappings_needed.append((service_name, external_port, internal_port))
                    elif isinstance(port_mapping, int):
                        internal_port = str(port_mapping)
                        port_mappings_needed.append((service_name, internal_port, internal_port))

            if challenge_internal_port is not None:
                internal_port_str = str(challenge_internal_port)
                services_with_port = {
                    service_name for service_name, _, internal_port in port_mappings_needed if internal_port == internal_port_str
                }
                if not services_with_port:
                    port_mappings_needed.append(("challenge", internal_port_str, internal_port_str))

            if port_mappings_needed:
                external_ports = get_multiple_available_ports(len(port_mappings_needed))
                for index, (service_name, _original_external_port, internal_port) in enumerate(port_mappings_needed):
                    mapping_key = f"{service_name}:{internal_port}"
                    port_mappings[mapping_key] = external_ports[index]
                    if len(port_mappings_needed) == 1:
                        port_mappings[internal_port] = external_ports[index]

            if port_mappings:
                actual_compose_path = create_dynamic_docker_compose(
                    docker_compose_path,
                    container_name_suffix,
                    dynamic_network_name,
                    port_mappings,
                )
        except Exception as exc:
            logger.warning("Failed to prepare dynamic docker-compose, falling back to original file: %s", exc)
            actual_compose_path = docker_compose_path
            port_mappings = {}

    challenge_name = docker_compose_path.parent.name
    raw_project_name = (
        f"{challenge_name}-{container_name_suffix}" if container_name_suffix else f"{challenge_name}-{int(time.time())}"
    )
    project_name = re.sub(r"[^a-z0-9_-]", "_", raw_project_name.lower())
    project_name = re.sub(r"[_-]+", "_", project_name)
    if not project_name or not project_name[0].isalnum():
        project_name = f"p{project_name or int(time.time())}"

    startup_cmd = [
        "docker",
        "compose",
        "-f",
        str(actual_compose_path),
        "-p",
        project_name,
        "up",
        "-d",
        "--force-recreate",
    ]
    compose_env = os.environ.copy()
    compose_env.update({
        "DOCKER_BUILDKIT": "1",
        "COMPOSE_DOCKER_CLI_BUILD": "0",
    })
    compose = subprocess.Popen(
        startup_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=str(docker_compose_path.parent),
        env=compose_env,
    )
    try:
        output, _ = compose.communicate(timeout=DOCKER_COMPOSE_STARTUP_DELAY)
    except subprocess.TimeoutExpired:
        compose.kill()
        raise RuntimeError(
            f"Docker Compose startup timed out after {DOCKER_COMPOSE_STARTUP_DELAY} seconds"
        )
    if compose.returncode != 0:
        raise RuntimeError(f"Docker Compose startup failed with return code {compose.returncode}: {output}")
    return actual_compose_path, port_mappings, project_name


def copy_file_to_container(container: Container, contents: str, container_path: str) -> None:
    data = contents.encode()
    tar_stream = BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        info = tarfile.TarInfo(name=Path(container_path).name)
        info.size = len(data)
        tar.addfile(info, BytesIO(data))
    tar_stream.seek(0)
    container.exec_run(f"mkdir -p {shlex.quote(str(Path(container_path).parent))}")
    container.put_archive(str(Path(container_path).parent), tar_stream.read())


def copy_anything_to_container(container: Container, host_path: str, container_path: str) -> None:
    source = Path(host_path)
    if not source.exists():
        raise FileNotFoundError(f"Host path not found: {host_path}")
    tar_stream = BytesIO()
    with tarfile.open(fileobj=tar_stream, mode="w") as tar:
        tar.add(source, arcname=source.name)
    tar_stream.seek(0)
    container.exec_run(f"mkdir -p {shlex.quote(container_path)}")
    container.put_archive(container_path, tar_stream.read())


def read_with_timeout(
    process: subprocess.Popen,
    _unused: Any | None = None,
    timeout_duration: int | float = 25,
) -> str:
    fd = process.stdout.fileno()  # type: ignore[union-attr]
    chunks: list[str] = []
    end_time = time.time() + timeout_duration
    while time.time() < end_time:
        ready, _, _ = select.select([fd], [], [], 0.1)
        if not ready:
            continue
        data = os.read(fd, 4096)
        if not data:
            break
        chunks.append(data.decode(errors="replace"))
    return "".join(chunks)


def read_with_timeout_experimental(
    process: subprocess.Popen,
    timeout_duration: int | float = 25,
    no_output_timeout_duration: int | float = 25,
) -> tuple[str, str]:
    fd = process.stdout.fileno()  # type: ignore[union-attr]
    chunks: list[str] = []
    start_time = time.time()
    last_output = time.time()
    while True:
        if time.time() - start_time > timeout_duration:
            raise TimeoutError("Command execution timed out")
        if time.time() - last_output > no_output_timeout_duration:
            raise NoOutputTimeoutError("No output timeout")
        ready, _, _ = select.select([fd], [], [], 0.1)
        if not ready:
            continue
        data = os.read(fd, 4096)
        if not data:
            break
        decoded = data.decode(errors="replace")
        chunks.append(decoded)
        last_output = time.time()
        current = "".join(chunks)
        match = PROCESS_DONE_REGEX.search(current)
        if match:
            exit_code = match.group(1)
            body = PROCESS_DONE_REGEX.sub("", current).rstrip("\n")
            return body, exit_code


def read_session_with_timeout(
    process: subprocess.Popen,
    terminal_pattern: str,
    timeout_duration: int | float = 25,
    no_output_timeout_duration: int | float = 25,
) -> str:
    fd = process.stdout.fileno()  # type: ignore[union-attr]
    chunks: list[str] = []
    start_time = time.time()
    last_output = time.time()
    while True:
        if time.time() - start_time > timeout_duration:
            raise TimeoutError("Interactive session timeout")
        if time.time() - last_output > no_output_timeout_duration:
            raise NoOutputTimeoutError("Interactive session no output timeout")
        ready, _, _ = select.select([fd], [], [], 0.1)
        if not ready:
            continue
        data = os.read(fd, 4096)
        if not data:
            break
        decoded = data.decode(errors="replace")
        chunks.append(decoded)
        last_output = time.time()
        if terminal_pattern in "".join(chunks):
            return "".join(chunks)
    return "".join(chunks)


def attach_network_interface_to_container(container_name: str, network_name: str) -> None:
    client = docker.from_env()
    max_retries = 8
    base_delay = 3

    for attempt in range(max_retries):
        try:
            network = client.networks.get(network_name)
            container = client.containers.get(container_name)
            try:
                network.connect(container)
            except docker.errors.APIError as exc:
                if "already exists" not in str(exc).lower():
                    raise
            return
        except docker.errors.NotFound:
            if attempt == max_retries - 1:
                raise
            time.sleep(base_delay * (2**attempt))


def ensure_docker_network(network_name: str, driver: str = "bridge") -> None:
    client = docker.from_env()
    names = {network.name for network in client.networks.list(names=[network_name])}
    if network_name in names:
        return
    client.networks.create(network_name, driver=driver)


def cleanup_dynamic_network(network_name: str) -> None:
    if not network_name or network_name == "ctfnet":
        return
    try:
        client = docker.from_env()
        network = client.networks.get(network_name)
        try:
            network.reload()
            for container_id in (network.attrs.get("Containers") or {}).keys():
                try:
                    container = client.containers.get(container_id)
                    network.disconnect(container, force=True)
                except Exception:
                    pass
        except Exception:
            pass
        network.remove()
    except docker.errors.NotFound:
        return
    except Exception as exc:
        logger.warning("Failed to remove dynamic network %s: %s", network_name, exc)


def cleanup_all_dynamic_networks() -> None:
    """Compatibility helper copied from enigma-plus."""
    try:
        client = docker.from_env()
        networks = client.networks.list()
        dynamic_networks = [network for network in networks if network.name.startswith("ctfnet-")]
        for network in dynamic_networks:
            cleanup_dynamic_network(network.name)
    except Exception as exc:
        logger.warning("Unexpected error during dynamic network cleanup: %s", exc)


def cleanup_dynamic_resources() -> None:
    """Compatibility helper copied from enigma-plus."""
    cleanup_all_dynamic_networks()

    try:
        for temp_file in Path("/tmp").glob("docker-compose-*"):
            try:
                temp_file.unlink()
            except FileNotFoundError:
                pass
            except Exception as exc:
                logger.warning("Failed to remove temporary file %s: %s", temp_file, exc)
    except Exception as exc:
        logger.warning("Error during temporary docker-compose file cleanup: %s", exc)


def check_docker_subnet_availability(wait_for_space: bool = False, max_wait_time: int = 300) -> dict[str, int]:
    try:
        client = docker.from_env()
        networks = client.networks.list()
        total_networks = len(networks)
        bridge_networks = len([n for n in networks if n.attrs.get("Driver") == "bridge"])
        dynamic_networks = len([n for n in networks if n.name.startswith("ctfnet-")])
        status = {
            "total_networks": total_networks,
            "bridge_networks": bridge_networks,
            "dynamic_networks": dynamic_networks,
            "subnet_usage_warning": False,
            "subnet_usage_critical": False,
        }
        logger.debug("Docker network status: %s", status)
        return status
    except Exception as exc:
        logger.warning("Failed to check Docker subnet availability: %s", exc)
        return {"error": str(exc)}


def wait_for_docker_subnet_space(
    max_wait_time: int = 300,
    check_interval: int = 10,
    target_free_networks: int = 5,
) -> bool:
    """Compatibility shim kept for parity with enigma-plus."""
    del max_wait_time, check_interval, target_free_networks
    logger.debug("Subnet space restrictions disabled - proceeding without limitations")
    return True
