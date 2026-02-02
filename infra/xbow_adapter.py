"""
Xbow 环境适配器
将 Xbow Docker 环境转换为标准接口

python .local_workspace/test_xbow_setup_teardown.py


"""

import subprocess
import time
from pathlib import Path
from typing import Tuple, Dict, Any
import tempfile
import docker

from .env_adapter import BaseEnvAdapter
from .env_types import StandardAction, ActionType


class XbowAdapter(BaseEnvAdapter):
    """
    Xbow 适配器
    
    负责：
    1. 启动/关闭 Xbow Docker Compose 环境
    2. 标准化 Xbow 的输入输出
    3. 在 attacker 容器内执行工具
    """

    def __init__(self, config: Dict[str, Any]):
        """
        初始化 Xbow 适配器
        
        Args:
            config: 环境配置字典
        """
        super().__init__(config)

        # Xbow 特定配置
        # Note: SecurityEnv unpacks backend_config into adapter config,
        # so we read directly from config, not from config["backend_config"]
        self.xbow_path = config.get("xbow_path", "")
        self.compose_path = config.get("compose_path")
        self.benchmark_id = config.get("benchmark_id", "")

        # Docker 客户端
        self.docker_client = docker.from_env()
        self.compose_cmd = self._detect_compose_command()

        # 项目名称
        # For Xbow, use the benchmark ID as project name to match pre-built images
        # The benchmark directory naturally provides isolation
        # Keep hyphens to match the image names created by make build
        self.project_name = config["task_id"].lower()  # e.g., "xben-001-24"
        
        # Use UUID for attacker network to avoid conflicts in parallel execution
        import uuid
        self.network_name = f"xbow_net_{uuid.uuid4().hex[:8]}"

        # 容器引用
        self.target_container = None
        self.attacker_container = None
        self.service_url = None
        self.network_name = None

        # Xbow 元数据
        self.metadata = {}

    def _detect_compose_command(self):
        """检测 docker-compose 命令"""
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
        return ["docker-compose"]

    # ========================================================================
    # 必须实现的抽象方法（从 BaseEnvAdapter 继承）
    # ========================================================================

    def setup(self) -> None:
        """启动 Xbow 环境"""
        print(f"[XbowAdapter] Starting Xbow: {self.config['task_id']}")
        
        # Validate and resolve compose_path
        if not self.compose_path:
            raise ValueError("compose_path not specified in backend_config")
        
        # Resolve compose path relative to repository root
        compose_path = Path(self.compose_path).expanduser()
        if not compose_path.is_absolute():
            # Find repository root (where pyproject.toml exists)
            repo_root = Path(__file__).parent.parent
            compose_path = repo_root / compose_path
        
        compose_path = compose_path.resolve()
        print(f"[XbowAdapter] Compose path: {compose_path}")
        
        if not compose_path.exists():
            raise FileNotFoundError(f"Xbow compose file not found: {compose_path}")
        
        # 启动 docker-compose (使用 --wait 等待 healthcheck)
        print(f"[XbowAdapter] Starting docker-compose with project: {self.project_name}")
        result = subprocess.run(
            self.compose_cmd + ["-p", self.project_name, "-f", str(compose_path), "up", "-d", "--wait"],
            cwd=compose_path.parent,
            capture_output=True,
            text=True,
            timeout=180  # 3 minutes timeout for complex benchmarks
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Failed to start Xbow: {result.stderr}")
        
        print(f"[XbowAdapter] Docker containers started, discovering services...")
        
        # 发现目标容器
        self._discover_containers(compose_path.parent)
        
        # 启动 attacker 容器
        self._start_attacker()
        
        # 构建服务 URL
        self._construct_service_url()
        
        print(f"[XbowAdapter] Environment ready: {self.service_url}")

    def teardown(self) -> None:
        """清理 Xbow 环境"""
        print(f"[XbowAdapter] Tearing down: {self.config['task_id']}")
        
        try:
            # 停止 attacker
            if self.attacker_container:
                try:
                    self.attacker_container.stop()
                    print(f"[XbowAdapter] Attacker container stopped")
                except Exception as e:
                    print(f"[XbowAdapter] Warning: Failed to stop attacker: {e}")
            
            # 停止 docker-compose
            if self.compose_path:
                # Resolve compose path the same way as in setup()
                compose_path = Path(self.compose_path).expanduser()
                if not compose_path.is_absolute():
                    repo_root = Path(__file__).parent.parent
                    compose_path = repo_root / compose_path
                
                compose_path = compose_path.resolve()
                
                if compose_path.exists():
                    print(f"[XbowAdapter] Stopping docker-compose...")
                    result = subprocess.run(
                        self.compose_cmd + ["-p", self.project_name, "-f", str(compose_path), "down", "-v"],
                        cwd=compose_path.parent,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    
                    if result.returncode == 0:
                        print(f"[XbowAdapter] Docker-compose stopped successfully")
                    else:
                        print(f"[XbowAdapter] Warning: docker-compose down returned {result.returncode}")
                        if result.stderr:
                            print(f"[XbowAdapter] Stderr: {result.stderr}")
                else:
                    print(f"[XbowAdapter] Warning: Compose file not found: {compose_path}")
        except Exception as e:
            print(f"[XbowAdapter] Cleanup error: {e}")

    def reset_backend(self) -> str:
        """
        重置 Xbow 环境
        
        Returns:
            任务描述字符串（未标准化的文本）
            
        TODO: 实现逻辑
        1. 清理 attacker 容器状态（如果需要）
        2. 重置环境变量（如果需要）
        3. 生成任务描述
        4. 返回初始观察值
        """
        raise NotImplementedError("XbowAdapter.reset_backend() not implemented yet")

    def step_backend(self, action: StandardAction) -> Tuple[str, float, bool, Dict]:
        """
        在 Xbow 环境执行动作
        
        Args:
            action: 标准化的动作
            
        Returns:
            (observation, reward, done, info) - 底层环境的原始返回值
            
        TODO: 实现逻辑
        1. 根据 action.action_type 选择工具
           - ActionType.BASH: 执行 bash 命令
           - ActionType.HTTP_REQUEST: 发送 HTTP 请求
        2. 在 attacker 容器内执行
        3. 捕获输出
        4. 返回 (output_str, 0.0, False, {})
        """
        raise NotImplementedError("XbowAdapter.step_backend() not implemented yet")

    def _get_target_info(self) -> Dict[str, Any]:
        """获取目标信息"""
        return {
            "host": self.config.get("target_host", "unknown"),
            "port": self.config.get("target_port", 80),
            "protocol": self.config.get("target_protocol", "http"),
            "url": self.service_url or "",
            "metadata": self.metadata
        }
    
    # ========================================================================
    # Xbow 特定辅助方法
    # ========================================================================
    
    def _discover_containers(self, compose_dir: Path):
        """发现 Xbow 目标容器"""
        # 获取所有容器
        result = subprocess.run(
            self.compose_cmd + ["-p", self.project_name, "ps", "-q"],
            cwd=compose_dir,
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("No containers found for Xbow environment")
        
        container_ids = result.stdout.strip().split('\n')
        
        # 基础设施服务黑名单 (从分析中得出)
        INFRASTRUCTURE_SERVICES = {
            'db', 'database', 'mysql', 'postgres', 'postgresql',
            'mongodb', 'mongo', 'redis', 'memcached',
            'nginx', 'haproxy', 'mitmproxy', 'traefik',
            's3', 'minio', 'internal-service'
        }
        
        # 查找目标容器 (排除基础设施服务)
        for container_id in container_ids:
            try:
                container = self.docker_client.containers.get(container_id)
                service_name = container.labels.get('com.docker.compose.service', '')
                
                # 跳过基础设施服务
                if service_name.lower() in INFRASTRUCTURE_SERVICES:
                    print(f"[XbowAdapter] Skipping infrastructure service: {service_name}")
                    continue
                
                # 找到目标服务
                print(f"[XbowAdapter] Found target service: {service_name}")
                self.target_container = container
                
                # 获取网络信息
                networks = list(container.attrs['NetworkSettings']['Networks'].keys())
                self.network_name = networks[0] if networks else None
                
                # 保存服务名和端口到 config
                self.config['target_host'] = service_name
                
                # 尝试从容器配置中提取端口
                exposed_ports = container.attrs['Config'].get('ExposedPorts', {})
                if exposed_ports:
                    # 获取第一个暴露的端口
                    port_spec = list(exposed_ports.keys())[0]
                    port = int(port_spec.split('/')[0])
                    self.config['target_port'] = port
                    print(f"[XbowAdapter] Detected port: {port}")
                
                break
            except Exception as e:
                print(f"[XbowAdapter] Error inspecting container {container_id}: {e}")
                continue
        
        if not self.target_container:
            # 如果没有找到非基础设施服务，就用第一个容器
            print(f"[XbowAdapter] Warning: No target service found, using first container")
            self.target_container = self.docker_client.containers.get(container_ids[0])
            networks = list(self.target_container.attrs['NetworkSettings']['Networks'].keys())
            self.network_name = networks[0] if networks else None
    
    def _start_attacker(self):
        """启动攻击者容器"""
        try:
            # 检查镜像
            try:
                self.docker_client.images.get("cve-attacker:latest")
            except:
                self._build_attacker_image()
            
            # 启动容器
            self.attacker_container = self.docker_client.containers.run(
                "cve-attacker:latest",
                name=f"attacker_{self.project_name}",
                network=self.network_name,
                detach=True,
                remove=True,
                command="tail -f /dev/null"
            )
        except Exception as e:
            print(f"[XbowAdapter] Warning: Failed to start attacker: {e}")
    
    def _build_attacker_image(self):
        """构建攻击者镜像"""
        
        dockerfile = """FROM python:3.11-slim
RUN apt-get update && apt-get install -y curl wget netcat-traditional nmap dnsutils iputils-ping && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir requests
WORKDIR /attacker
CMD ["tail", "-f", "/dev/null"]
"""
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "Dockerfile").write_text(dockerfile)
            self.docker_client.images.build(path=tmpdir, tag="cve-attacker:latest", rm=True)
    
    def _construct_service_url(self):
        """构建服务 URL"""
        target_host = self.config.get("target_host", "target")
        target_port = self.config.get("target_port", 80)
        protocol = self.config.get("target_protocol", "http")
        self.service_url = f"{protocol}://{target_host}:{target_port}"
