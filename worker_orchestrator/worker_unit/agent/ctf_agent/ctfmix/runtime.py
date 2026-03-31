"""CTFMix runtime: a small EnIGMA-style execution core for VulRL."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import docker

from .agents import AgentConfig
from .interactive_commands import (
    INTERACTIVE_SESSIONS_CONFIG,
    InteractiveSession,
    get_interactive_commands,
    get_interactive_session,
)
from .log import get_logger
from .prompt import build_instance_prompt, load_default_agent_config
from .runtime_utils import (
    PROCESS_DONE_MARKER_END,
    PROCESS_DONE_MARKER_START,
    attach_network_interface_to_container,
    check_docker_subnet_availability,
    cleanup_dynamic_network,
    copy_anything_to_container,
    copy_file_to_container,
    ensure_docker_network,
    get_docker_compose,
    read_with_timeout_experimental,
)
from .types import AgentInfo

TASK_EXECUTION_TIMEOUT = float(os.environ.get("SWE_AGENT_TASK_TIMEOUT", "900"))
MODEL_GENERATION_TIMEOUT = float(os.environ.get("SWE_AGENT_MODEL_GENERATION_TIMEOUT", "300"))
CTF_SERVER_VALIDATION_TIMEOUT = float(os.environ.get("SWE_AGENT_CTF_SERVER_VALIDATION_TIMEOUT", "25"))
CONTAINER_HEALTH_CHECK_TIMEOUT = float(os.environ.get("SWE_AGENT_CONTAINER_HEALTH_CHECK_TIMEOUT", "10"))


@dataclass
class RuntimeTask:
    task_id: str
    compose_path: str | None = None
    flag: str | None = None
    flag_sha256: str | None = None
    flag_check: str | None = None
    box: str = ""
    internal_port: int = 0
    repo_path: str | None = None
    files: list[str] = field(default_factory=list)
    name: str = "ctf-task"
    description: str = ""
    category: str = "misc"
    category_friendly: str = "miscellaneous"
    points: int | str = "unknown"
    flag_format: str = "flag{...}"
    server_description: str = ""
    image_name: str = "sweagent/enigma:latest"
    command_config: str | None = None
    enable_dynamic_ports: bool = False
    exclude_paths: list[str] = field(default_factory=list)
    expose_flag_to_agent: bool = False
    hide_solution_artifacts: bool = True

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuntimeTask":
        return cls(**data)


class CTFMixRuntime:
    def __init__(self, task: RuntimeTask | dict[str, Any], config_path: str | Path | None = None):
        self.task = task if isinstance(task, RuntimeTask) else RuntimeTask.from_dict(task)
        self.name = f"ctfmix::{self.task.task_id}"
        self.record = {"instance_id": self.task.task_id}
        self.logger = get_logger("CTFMixRuntime")
        self.agent_config: AgentConfig = load_default_agent_config(config_path or self.task.command_config)
        self.docker_client = docker.from_env()
        self.container_name: str | None = None
        self.container_obj = None
        self.container: subprocess.Popen | None = None
        self.compose_project_name: str | None = None
        self.runtime_compose_path: Path | None = None
        self.challenge_network: str | None = None
        self.dynamic_network_name: str | None = None
        self.port_mappings: dict[str, int] = {}
        self.interactive_session: InteractiveSession | None = None
        self.returncode: int | None = None
        self.communicate_output: str = ""
        self.terminal_reward: float | None = None
        self.last_submission_result: dict[str, Any] | None = None
        self.last_non_submission_observation: str = ""
        self._prepared = False

    @staticmethod
    def _normalized_state(state: dict[str, Any] | None) -> dict[str, str]:
        state = state or {}
        return {
            "open_file": str(state.get("open_file", "n/a")),
            "working_dir": str(state.get("working_dir", ".")),
            "interactive_session": str(state.get("interactive_session", "n/a")),
        }

    def _get_container_name(self) -> str:
        return f"ctfmix-{self.task.task_id.replace('/', '-').replace('_', '-').lower()}-{uuid.uuid4().hex[:8]}"

    def _get_unique_container_suffix(self) -> str:
        return f"{os.getpid()}-{int(time.time())}-{uuid.uuid4().hex[:8]}"

    def prepare(self) -> None:
        if self._prepared:
            return
        self._reset_container()
        self._prepared = True

    def _reset_container(self) -> None:
        if self.container is not None:
            try:
                self.container.terminate()
            except Exception:
                pass
        self._init_container()  # start agent docker
        self._init_scripts()

    def _init_container(self) -> None:
        self.container_name = self._get_container_name()
        self.container_obj = self.docker_client.containers.run(
            self.task.image_name,
            name=self.container_name,
            detach=True,
            remove=True,
            tty=True,
            stdin_open=True,
            command="tail -f /dev/null",
        )
        self.container = subprocess.Popen(
            ["docker", "exec", "-i", self.container_name, "/bin/bash", "-l"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            bufsize=0,
        )
        time.sleep(1)
        self.logger.info("Started runtime container %s", self.container_name)

    def _init_scripts(self) -> None:
        self.communicate_with_handling("source /root/.bashrc", "Failed to source .bashrc")
        self.communicate_with_handling("mkdir -p /root/commands", "Failed to create commands directory")
        self.communicate_with_handling("touch /root/commands/__init__.py", "Failed to create commands init")
        self.communicate_with_handling("export PATH=$PATH:/root/commands", "Failed to export commands path")

    def _init_docker_compose(self) -> None:
        if not self.task.compose_path:
            return
        compose_path = Path(self.task.compose_path).expanduser().resolve()
        import yaml

        compose_data = yaml.safe_load(compose_path.read_text()) or {}
        for network_name, network_config in (compose_data.get("networks") or {}).items():
            if isinstance(network_config, dict) and network_config.get("external") and not self.task.enable_dynamic_ports:
                ensure_docker_network(network_name)
        if self.task.enable_dynamic_ports:
            check_docker_subnet_availability()
            container_suffix = self._get_unique_container_suffix()
            self.dynamic_network_name = f"ctfnet-{container_suffix}"
            ensure_docker_network(self.dynamic_network_name)
            runtime_compose_path, self.port_mappings, actual_project_name = get_docker_compose(
                compose_path,
                container_name_suffix=container_suffix,
                dynamic_ports=True,
                challenge_internal_port=self.task.internal_port or None,
            )
            self.challenge_network = self.dynamic_network_name
        else:
            self.dynamic_network_name = None
            self.port_mappings = {}
            runtime_compose_path = compose_path
            actual_project_name = f"ctfmix_{compose_path.parent.name}_{uuid.uuid4().hex[:8]}".lower()
            normalized_compose, modified = self._normalize_compose(compose_path)
            if modified:
                runtime_compose_path = normalized_compose
            result = subprocess.run(
                ["docker", "compose", "-f", str(runtime_compose_path), "-p", actual_project_name, "up", "-d"],
                cwd=compose_path.parent,
                capture_output=True,
                text=True,
                timeout=180,
            )
            if result.returncode != 0:
                raise RuntimeError(f"Failed to start docker compose: {result.stderr}")

        self.runtime_compose_path = runtime_compose_path
        self.compose_project_name = actual_project_name

        # load docker-compose.yml
        self.docker_compose_yml = yaml.safe_load(self.runtime_compose_path.read_text())

        ps = subprocess.run(
            ["docker", "compose", "-f", str(runtime_compose_path), "-p", self.compose_project_name, "ps", "-q"],
            cwd=compose_path.parent,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if ps.returncode != 0 or not ps.stdout.strip():
            raise RuntimeError("Failed to discover challenge containers after compose up")
        container_id = ps.stdout.strip().splitlines()[0]
        challenge_container = self.docker_client.containers.get(container_id)
        networks = list(challenge_container.attrs["NetworkSettings"]["Networks"].keys())
        if not self.challenge_network:
            self.challenge_network = networks[0] if networks else None
        if self.challenge_network:
            attach_network_interface_to_container(self.container_name, self.challenge_network)
        time.sleep(10 if self.task.enable_dynamic_ports else 5)
        self.logger.info("Started challenge compose project %s", self.compose_project_name)

    def _normalize_compose(self, compose_path: Path) -> tuple[Path, bool]:
        import yaml

        compose_data = yaml.safe_load(compose_path.read_text()) or {}
        services = compose_data.get("services")
        modified = False
        if not isinstance(services, dict):
            return compose_path, modified

        rewritten_services: dict[str, Any] = {}
        for service_name, service_config in services.items():
            if not isinstance(service_config, dict):
                rewritten_services[service_name] = service_config
                continue
            service_copy = dict(service_config)
            if "container_name" in service_copy:
                service_copy.pop("container_name", None)
                modified = True
            rewritten_services[service_name] = service_copy
        compose_data["services"] = rewritten_services

        if not modified:
            return compose_path, modified

        normalized_path = compose_path.parent / f"ctfmix-compose-{uuid.uuid4().hex[:8]}.yml"
        normalized_path.write_text(yaml.safe_dump(compose_data, sort_keys=False))
        return normalized_path, modified

    def _validate_ctf_server_connectivity(self) -> bool:
        return self._validate_ctf_server_connectivity_impl(allow_restart=True)

    def _validate_container_health(self) -> bool:
        try:
            result = self.communicate("echo 'health_check'", timeout_duration=CONTAINER_HEALTH_CHECK_TIMEOUT)
            return "health_check" in result
        except Exception as exc:
            self.logger.debug("Container health check failed: %s", exc)
            return False

    def _safe_communicate_with_retry(
        self,
        command: str,
        timeout_duration: int | float = 25,
        max_retries: int = 3,
        no_output_timeout_duration: int | float | None = None,
    ) -> str | None:
        last_error: Exception | None = None
        for attempt in range(max_retries):
            if not self._validate_container_health():
                self.logger.warning("Container is unhealthy before command attempt %s/%s", attempt + 1, max_retries)
                return None
            try:
                return self.communicate(
                    command,
                    timeout_duration=timeout_duration,
                    no_output_timeout_duration=no_output_timeout_duration,
                )
            except Exception as exc:
                last_error = exc
                self.logger.debug(
                    "Command attempt %s/%s failed: %s",
                    attempt + 1,
                    max_retries,
                    exc,
                )
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))
        if last_error is not None:
            self.logger.debug("Command failed after retries: %s", last_error)
        return None

    def _lightweight_server_validation(self, server_name: str, internal_port: int) -> bool:
        cmd = (
            f"timeout 5 bash -c 'echo > /dev/tcp/{shlex.quote(server_name)}/{int(internal_port)}' "
            "2>/dev/null && echo SUCCESS || echo SUCCESS"
        )
        result = self._safe_communicate_with_retry(cmd, timeout_duration=10, max_retries=1)
        return result is not None and "SUCCESS" in result

    def _validate_ctf_server_connectivity_impl(self, allow_restart: bool) -> bool:
        if not self.task.compose_path:
            return True
        if not self.task.box or not self.task.internal_port:
            return True

        if self.task.enable_dynamic_ports:
            import random

            time.sleep(random.uniform(1, 5))

        try:
            containers = self.docker_client.containers.list()
            parallel_count = sum(
                1
                for container in containers
                if container.status == "running"
                and container.name.startswith("ctfmix-")
                and container.name != self.container_name
            )
            if self.task.enable_dynamic_ports and parallel_count >= 10:
                self.logger.warning(
                    "High parallel load detected (%s runtime containers). Using lightweight validation.",
                    parallel_count,
                )
                return self._lightweight_server_validation(self.task.box, self.task.internal_port)
        except Exception as exc:
            self.logger.debug("Could not determine parallel runtime load: %s", exc)

        time.sleep(10 if self.task.enable_dynamic_ports else 30)
        if not self._validate_container_health():
            self.logger.error("Runtime container became unhealthy before CTF validation")
            return False

        resolved_ip: str | None = None
        try:
            dns_check = self._safe_communicate_with_retry(
                f"getent hosts {shlex.quote(self.task.box)} 2>/dev/null || true",
                timeout_duration=10,
                max_retries=1,
            )
            if dns_check:
                for line in dns_check.splitlines():
                    parts = line.strip().split()
                    if parts:
                        candidate = parts[0]
                        if re.match(r"^\d{1,3}(\.\d{1,3}){3}$", candidate) and not candidate.startswith("127."):
                            resolved_ip = candidate
                            break
        except Exception as exc:
            self.logger.debug("DNS resolution diagnostic failed: %s", exc)

        if self.task.category in {"web", "misc"}:
            web_target = resolved_ip or self.task.box
            test_commands = [
                f"curl -f --connect-timeout 5 --max-time 10 http://{shlex.quote(web_target)}:{int(self.task.internal_port)}/ > /dev/null 2>&1 && echo SUCCESS || echo FAILED",
                f"nc -z -v -w5 {shlex.quote(self.task.box)} {int(self.task.internal_port)} 2>&1 && echo SUCCESS || echo FAILED",
            ]
        else:
            tcp_target = resolved_ip or self.task.box
            test_commands = [
                f"nc -z -v -w5 {shlex.quote(self.task.box)} {int(self.task.internal_port)} 2>&1 && echo SUCCESS || echo FAILED",
                f"timeout 5 bash -c 'echo > /dev/tcp/{shlex.quote(tcp_target)}/{int(self.task.internal_port)}' 2>/dev/null && echo SUCCESS || echo FAILED",
            ]

        for attempt in range(5):
            if not self._validate_container_health():
                self.logger.error("Runtime container became unhealthy during CTF validation")
                return False
            for cmd in test_commands:
                result = self._safe_communicate_with_retry(
                    cmd,
                    timeout_duration=CTF_SERVER_VALIDATION_TIMEOUT,
                    max_retries=1,
                    no_output_timeout_duration=10,
                )
                if result is not None and "SUCCESS" in result:
                    return True
            self.logger.warning(
                "Challenge service %s:%s not reachable yet (attempt %s/5)",
                self.task.box,
                self.task.internal_port,
                attempt + 1,
            )
            wait_time = 5 + (attempt * 2) if self.task.enable_dynamic_ports else min(10 + (attempt * 5), 30)
            time.sleep(wait_time)
        if allow_restart and self._restart_ctf_services_and_retry_validation():
            return True
        return False

    def _restart_ctf_services_and_retry_validation(self) -> bool:
        if not self.compose_project_name or not self.task.compose_path:
            return False

        compose_path = Path(self.task.compose_path).expanduser().resolve()
        runtime_compose_path = self.runtime_compose_path or compose_path
        max_restart_attempts = 2 if self.task.enable_dynamic_ports else 1

        for restart_attempt in range(max_restart_attempts):
            self.logger.info("Restarting CTF services (%s/%s)", restart_attempt + 1, max_restart_attempts)
            restart_cmd = [
                "docker",
                "compose",
                "-f",
                str(runtime_compose_path),
                "-p",
                self.compose_project_name,
                "restart",
            ]
            result = subprocess.run(
                restart_cmd,
                capture_output=True,
                text=True,
                timeout=60,
                cwd=str(compose_path.parent),
            )
            if result.returncode != 0:
                self.logger.warning("Docker compose restart warning: %s", result.stderr.strip())

            restart_wait_time = 20 if self.task.enable_dynamic_ports else 30
            time.sleep(restart_wait_time)

            if self.challenge_network and self.container_name:
                try:
                    attach_network_interface_to_container(self.container_name, self.challenge_network)
                except Exception as exc:
                    self.logger.debug("Network re-attach after restart failed: %s", exc)

            if self._validate_ctf_server_connectivity_impl(allow_restart=False):
                return True

            if restart_attempt < max_restart_attempts - 1:
                delay = 10 * (restart_attempt + 1)
                time.sleep(delay)
        return False

    def _copy_repo(self) -> None:
        if not self.task.repo_path:
            self.communicate_with_handling("mkdir -p /workspace && cd /workspace", "Failed to enter default workspace")
            return
        repo_path = Path(self.task.repo_path).expanduser().resolve()
        if not repo_path.exists():
            raise FileNotFoundError(f"repo_path not found: {repo_path}")
        repo_name = repo_path.name
        repo_root = f"/{repo_name}"
        quoted_repo_root = shlex.quote(repo_root)
        self.communicate_with_handling(f"mkdir -p {quoted_repo_root}", f"Failed to create {repo_root}")
        for file_name in self.task.files:
            source_path = (repo_path / file_name).resolve()
            if not source_path.exists():
                raise FileNotFoundError(f"task file not found: {source_path}")
            relative_path = Path(file_name)
            target_parent = relative_path.parent.as_posix()
            container_parent = repo_root if target_parent in {"", "."} else f"{repo_root}/{target_parent}"
            self.communicate_with_handling(
                f"mkdir -p {shlex.quote(container_parent)}",
                f"Failed to create parent directory for {file_name}",
            )
            copy_anything_to_container(self.container_obj, str(source_path), container_parent)
        self.communicate_with_handling(
            f"chown -R root:root {quoted_repo_root} && cd {quoted_repo_root} && export ROOT=$(pwd -P)",
            "Failed to enter copied repo",
        )
        self._sanitize_repo_contents()

    def _hidden_repo_paths(self) -> list[str]:
        hidden_paths = list(self.task.exclude_paths)
        if self.task.hide_solution_artifacts:
            hidden_paths.extend(["metadata/solution", "solution", "flag.txt"])
        deduped: list[str] = []
        for path in hidden_paths:
            normalized = path.strip().strip("/")
            if normalized and normalized not in deduped:
                deduped.append(normalized)
        return deduped

    def _visible_prompt_files(self) -> list[str]:
        hidden_paths = self._hidden_repo_paths()
        visible_files: list[str] = []
        for file_path in self.task.files:
            normalized = file_path.strip().strip("/")
            if any(
                normalized == hidden_path or normalized.startswith(hidden_path + "/")
                for hidden_path in hidden_paths
            ):
                continue
            visible_files.append(file_path)
        return visible_files

    def build_prompt_task_payload(self) -> dict[str, Any]:
        payload = dict(self.task.__dict__)
        payload["files"] = self._visible_prompt_files()
        return payload

    def _sanitize_repo_contents(self) -> None:
        hidden_paths = self._hidden_repo_paths()
        if not hidden_paths:
            return
        for hidden_path in hidden_paths:
            escaped_path = shlex.quote(hidden_path)
            self.communicate_with_handling(
                f"if [ -e {escaped_path} ]; then rm -rf {escaped_path}; fi",
                f"Failed to remove hidden path {hidden_path}",
            )

    def _reset_environment_variables(self) -> None:
        cmd = [
            'export CURRENT_FILE=""',
            "export CURRENT_LINE=0",
            "export SEARCH_RESULTS=()",
            "export SEARCH_FILES=()",
            "export SEARCH_INDEX=0",
            'export INTERACTIVE_SESSION="n/a"',
        ]
        self.communicate_with_handling(" && ".join(cmd), "Failed to reset environment variables")

    def _clear_interactive_session_env(self) -> None:
        try:
            self.communicate("unset INTERACTIVE_SESSION", timeout_duration=5, no_output_timeout_duration=5)
        except Exception:
            self.logger.debug("Failed to clear INTERACTIVE_SESSION env var", exc_info=True)

    def _setup_ctf_flag(self) -> None:
        if not self.task.flag or not self.task.expose_flag_to_agent:
            return
        flag_setup_cmd = f"echo {shlex.quote(self.task.flag)} > /flag && chmod 400 /flag && ln -sf /flag /flag.txt"
        self.communicate_with_handling(flag_setup_cmd, "Failed to set up CTF flag file")

    def _load_state(self) -> dict[str, str]:
        output = self.communicate("state", timeout_duration=5, no_output_timeout_duration=5)
        try:
            return self._normalized_state(json.loads(output))
        except json.JSONDecodeError:
            return self._normalized_state(None)

    def _stop_compose_project(self) -> None:
        if not self.compose_project_name or not self.task.compose_path:
            return
        compose_path = Path(self.task.compose_path).expanduser().resolve()
        runtime_compose_path = self.runtime_compose_path or compose_path
        subprocess.run(
            ["docker", "compose", "-f", str(runtime_compose_path), "-p", self.compose_project_name, "down", "-v"],
            cwd=compose_path.parent,
            capture_output=True,
            timeout=60,
        )
        if runtime_compose_path != compose_path:
            try:
                runtime_compose_path.unlink()
            except FileNotFoundError:
                pass
        if self.dynamic_network_name:
            cleanup_dynamic_network(self.dynamic_network_name)
        self.runtime_compose_path = None
        self.compose_project_name = None
        self.challenge_network = None
        self.dynamic_network_name = None
        self.port_mappings = {}

    def reset(self) -> tuple[str, dict[str, Any]]:
        self.prepare()
        self.terminal_reward = None
        self.last_submission_result = None
        if self.interactive_session is not None:
            try:
                self.interactive_session.session_process.terminate()
            except Exception:
                pass
            self.interactive_session = None
        self._stop_compose_project()
        self._init_docker_compose()
        if not self._validate_ctf_server_connectivity():
            raise RuntimeError(f"CTF server {self.task.box}:{self.task.internal_port} is not reachable from runtime container")
        self._copy_repo()
        self._reset_environment_variables()
        self.agent_config.init_environment_vars(self)
        self._setup_ctf_flag()
        state = self._normalized_state(self._load_state())
        prompt = build_instance_prompt(self.agent_config, self.build_prompt_task_payload(), state)
        return prompt, {"state": state}

    def reset_for_new_attempt(self) -> None:
        if self.interactive_session is not None:
            try:
                self.interactive_session.session_process.terminate()
            except Exception:
                pass
            self.interactive_session = None

    def get_available_actions(self) -> list[str]:
        return []

    def _check_syntax(self, input: str) -> tuple[str, bool]:
        output = self._communicate(f"/bin/bash -n <<'EOF'\n{input}\nEOF\n", timeout_duration=10, no_output_timeout_duration=10)
        return output, self.returncode == 0

    def _communicate(self, input: str, timeout_duration: int | float = 25, no_output_timeout_duration: int | float = 25) -> str:
        assert self.container is not None
        command_suffix = f'EXITSTATUS="$?"; sleep 0.01; echo {PROCESS_DONE_MARKER_START}$EXITSTATUS{PROCESS_DONE_MARKER_END}\n'
        cmd = input if input.endswith("\n") else input + "\n"
        payload = (cmd + command_suffix).encode()
        os.write(self.container.stdin.fileno(), payload)  # type: ignore[arg-type]
        time.sleep(0.03)
        self.container.stdin.flush()  # type: ignore[union-attr]
        buffer, exit_code = read_with_timeout_experimental(
            self.container,
            timeout_duration=timeout_duration,
            no_output_timeout_duration=no_output_timeout_duration,
        )
        self.returncode = int(exit_code) if str(exit_code).isdigit() else 998
        return buffer

    def communicate(
        self,
        input: str,
        timeout_duration: int | float = 25,
        no_output_timeout_duration: int | float | None = None,
        *,
        set_last_action: bool = False,
    ) -> str:
        if no_output_timeout_duration is None:
            no_output_timeout_duration = timeout_duration
        if input.strip() == "exit":
            self.returncode = 0
            return ""
        output, valid = self._check_syntax(input)
        if not valid:
            return output
        output = self._communicate(input, timeout_duration=timeout_duration, no_output_timeout_duration=no_output_timeout_duration)
        self.communicate_output = output
        if set_last_action:
            last_action_string = shlex.quote(input.strip())
            self._communicate(f"export LAST_ACTION={last_action_string}", timeout_duration=5, no_output_timeout_duration=5)
        return output

    def communicate_with_handling(self, input: str, error_msg: str, timeout_duration: int | float = 25) -> str:
        logs = self.communicate(input, timeout_duration=timeout_duration)
        if self.returncode != 0:
            raise RuntimeError(f"{error_msg}: {logs}")
        return logs

    def add_commands(self, commands: list[dict[str, Any]]) -> None:
        for command in commands:
            name = command["name"]
            source_name = command.get("source_name", name)
            contents = command["contents"]
            source_path = f"/root/commands/{source_name}"
            copy_file_to_container(self.container_obj, contents, source_path)
            if command["type"] == "source_file":
                self.communicate_with_handling(
                    f"source {shlex.quote(source_path)}",
                    f"Failed to source {source_name}",
                )
            elif command["type"] in {"script", "utility"}:
                exec_path = f"/root/commands/{name}"
                if source_name.endswith(".py"):
                    wrapper = (
                        "#!/bin/bash\n"
                        f'python3 {shlex.quote(source_path)} "$@"\n'
                    )
                    copy_file_to_container(self.container_obj, wrapper, exec_path)
                elif source_name != name:
                    wrapper = (
                        "#!/bin/bash\n"
                        f'exec {shlex.quote(source_path)} "$@"\n'
                    )
                    copy_file_to_container(self.container_obj, wrapper, exec_path)
                else:
                    exec_path = source_path
                self.communicate_with_handling(
                    f"chmod +x {shlex.quote(exec_path)}",
                    f"Failed to chmod {name}",
                )
            else:
                raise ValueError(f"Invalid command type: {command['type']}")

    def get_submission(self, output: str) -> str | None:
        pattern = r"\<\<SUBMISSION\|\|(.*)\|\|SUBMISSION\>\>"
        match = re.search(pattern, output, re.DOTALL)
        if match is None:
            return None
        return match.group(1)

    def validate_submission(self, submission: str) -> bool:
        submission = submission.strip()
        if self.task.flag:
            return submission == self.task.flag or f"flag{{{submission}}}" == self.task.flag
        if self.task.flag_sha256:
            import hashlib

            raw = re.search(r".+?{(.+?)}", submission)
            extracted = raw.group(1) if raw else submission
            return (
                hashlib.sha256(extracted.encode()).hexdigest() == self.task.flag_sha256
                or hashlib.sha256(submission.encode()).hexdigest() == self.task.flag_sha256
            )
        if self.task.flag_check:
            result = subprocess.run([self.task.flag_check], input=submission + "\n", text=True, capture_output=True)
            return "incorrect" not in result.stdout.lower()
        return True

    def _handle_interactive_commands(self, observation: str) -> str:
        session_name, interactive_commands = get_interactive_commands(observation, logger=self.logger)
        if session_name is None:
            return observation
        if self.interactive_session is not None and self.interactive_session.name != session_name:
            return self.interactive_session._get_only_one_interactive_error_message_observation()
        result = ""
        cwd = self._load_state().get("working_dir", "/")
        if not cwd.startswith("/"):
            cwd = "/" if cwd == "." else cwd
        for command in interactive_commands:
            if command == "START":
                if self.interactive_session is not None:
                    return self.interactive_session._get_only_one_interactive_error_message_observation()
                start_obs, self.interactive_session = get_interactive_session(
                    ctr_name=self.container_name,
                    ctr_obj=self.container_obj,
                    cwd=cwd,
                    session_name=session_name,
                    config=INTERACTIVE_SESSIONS_CONFIG[session_name],
                    logger=self.logger,
                )
                result += start_obs
            elif command == "STOP":
                if self.interactive_session is not None:
                    self.interactive_session.session_process.terminate()
                    self.interactive_session = None
                    self._clear_interactive_session_env()
                    result += f"Interactive session {session_name!r} stopped successfully"
            else:
                if self.interactive_session is None:
                    result += f"Interactive session {session_name!r} is not running!"
                else:
                    obs, terminate = self.interactive_session.communicate_with_handling(command)
                    result += obs + "\n"
                    if terminate:
                        self.interactive_session = None
                        self._clear_interactive_session_env()
        return result

    def step(self, action: str) -> tuple[str | None, int, bool, AgentInfo]:
        info: AgentInfo = {}
        action = action.strip()
        if action == "skip":
            info["exit_status"] = "skipped"
            return "Skipped", 0, True, info
        if action == "exit_forfeit":
            info["exit_status"] = "exit_forfeit"
            return "Exited", 0, True, info
        observation = self.communicate(action, timeout_duration=25, no_output_timeout_duration=25, set_last_action=True)
        submission = self.get_submission(observation)
        if submission is not None:
            valid = self.validate_submission(submission)
            self.last_submission_result = {"submission": submission, "valid": valid}
            if valid:
                info["exit_status"] = "submitted"
                info["submission"] = submission
                info["score"] = 1.0
                self.terminal_reward = 1.0
                return submission, 0, True, info
            info["exit_status"] = "wrong_submission"
            info["submission"] = submission
            info["score"] = 0.0
            self.terminal_reward = 0.0
            hint_lines = [
                "Wrong flag!",
                f"Submitted: {submission}",
                "If your previous command printed a flag, copy that exact string and resubmit it unchanged.",
            ]
            recent_candidates = self._extract_flag_candidates(self.last_non_submission_observation)
            if recent_candidates:
                hint_lines.append("Recent candidate flags from the previous command output:")
                hint_lines.extend(f"- {candidate}" for candidate in recent_candidates[:3])
            return "\n".join(hint_lines), 0, False, info
        observation = self._handle_interactive_commands(observation)
        self.last_non_submission_observation = observation
        return observation, 0, False, info

    def _extract_flag_candidates(self, observation: str) -> list[str]:
        if not observation:
            return []
        prefix = self.task.flag_format.split("{", 1)[0].strip()
        if prefix:
            pattern = re.compile(rf"{re.escape(prefix)}\{{[^}}\n]+\}}")
        else:
            pattern = re.compile(r"[A-Za-z0-9_]+\{[^}\n]+\}")
        candidates: list[str] = []
        for match in pattern.findall(observation):
            if match not in candidates:
                candidates.append(match)
        return candidates

    def close(self) -> None:
        if self.interactive_session is not None:
            try:
                self.interactive_session.session_process.terminate()
            except Exception:
                pass
            self.interactive_session = None
        if self.container is not None:
            try:
                self.container.terminate()
            except Exception:
                pass
            self.container = None
        self._stop_compose_project()
        if self.container_obj is not None:
            try:
                self.container_obj.stop(timeout=5)
            except Exception:
                pass
            self.container_obj = None

    def __enter__(self) -> "CTFMixRuntime":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
