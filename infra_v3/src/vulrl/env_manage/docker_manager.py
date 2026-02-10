"""
Docker management utilities

Shared Docker operations for building images and managing containers
across all adapters.
"""

import tempfile
from pathlib import Path
from typing import Optional
import docker


class DockerManager:
    """Centralized Docker operations"""
    
    # Standard attacker image Dockerfile
    ATTACKER_DOCKERFILE = """FROM python:3.11-slim
RUN apt-get update && apt-get install -y \\
    curl \\
    wget \\
    netcat-traditional \\
    nmap \\
    dnsutils \\
    iputils-ping \\
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir requests
WORKDIR /attacker
CMD ["tail", "-f", "/dev/null"]
"""
    
    @classmethod
    def ensure_attacker_image(cls, image_name: str = "cve-attacker:latest") -> bool:
        """
        Ensure attacker image exists (build if needed)
        
        Can be called:
        - Once upfront by launcher (optimization)
        - Per-adapter as needed (safety)
        
        Either way, only builds once thanks to Docker caching.
        
        Args:
            image_name: Docker image tag
            
        Returns:
            True if image exists or was built successfully
        """
        client = docker.from_env()
        
        try:
            client.images.get(image_name)
            print(f"✓ Docker image '{image_name}' exists")
            return True
        except docker.errors.ImageNotFound:
            print(f"Building Docker image '{image_name}'...")
            try:
                with tempfile.TemporaryDirectory() as tmpdir:
                    dockerfile_path = Path(tmpdir) / "Dockerfile"
                    dockerfile_path.write_text(cls.ATTACKER_DOCKERFILE)
                    client.images.build(
                        path=tmpdir,
                        tag=image_name,
                        rm=True,
                        quiet=False
                    )
                print(f"✓ Built Docker image '{image_name}'")
                return True
            except Exception as e:
                print(f"✗ Failed to build Docker image: {e}")
                return False
    
    @classmethod
    def create_attacker_container(
        cls,
        name: str,
        network: str,
        image: str = "cve-attacker:latest",
        **kwargs
    ):
        """
        Create attacker container
        
        Will auto-build image if it doesn't exist.
        
        Args:
            name: Container name
            network: Docker network name
            image: Docker image to use
            **kwargs: Additional arguments for containers.run()
            
        Returns:
            Docker container object
        """
        # Ensure image exists
        cls.ensure_attacker_image(image)
        
        # Create container
        client = docker.from_env()
        
        default_kwargs = {
            "detach": True,
            "remove": True,
            "command": "tail -f /dev/null"
        }
        default_kwargs.update(kwargs)
        
        return client.containers.run(
            image,
            name=name,
            network=network,
            **default_kwargs
        )
    
    @staticmethod
    def detect_compose_command() -> list:
        """
        Detect docker-compose command (v1 vs v2)
        
        Returns:
            List of command parts: ["docker", "compose"] or ["docker-compose"]
        """
        import subprocess
        
        # Try docker compose (v2)
        try:
            result = subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                timeout=5
            )
            if result.returncode == 0:
                return ["docker", "compose"]
        except:
            pass
        
        # Fall back to docker-compose (v1)
        return ["docker-compose"]
    
    @staticmethod
    def cleanup_containers_by_prefix(prefix: str):
        """
        Clean up all containers with name starting with prefix
        
        Args:
            prefix: Container name prefix
        """
        client = docker.from_env()
        
        for container in client.containers.list(all=True):
            if container.name.startswith(prefix):
                try:
                    container.remove(force=True)
                    print(f"✓ Removed container: {container.name}")
                except Exception as e:
                    print(f"✗ Failed to remove container {container.name}: {e}")
    
    @staticmethod
    def cleanup_networks_by_prefix(prefix: str):
        """
        Clean up all networks with name starting with prefix
        
        Args:
            prefix: Network name prefix
        """
        client = docker.from_env()
        
        for network in client.networks.list():
            if network.name.startswith(prefix):
                try:
                    network.remove()
                    print(f"✓ Removed network: {network.name}")
                except Exception as e:
                    print(f"✗ Failed to remove network {network.name}: {e}")
