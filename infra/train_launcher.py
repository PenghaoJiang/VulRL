"""
SkyRL Unified Security Training Launcher
完整的训练启动器，支持 Vulhub 和 CTF 混合训练

用法:
    python train_launcher.py

支持的数据源：
- Vulhub: CVE 漏洞数据集
- CTF: CTF 挑战数据集（通过 dataset_converter.py 转换）

注意：
- 数据集需要先通过 dataset_converter.py 转换为统一格式
- 可以混合使用多种数据源进行训练
"""

import os
import sys
import subprocess
import shutil
import tempfile
from pathlib import Path


class TrainingLauncher:
    """CVE Exploit训练启动器"""

    def __init__(self):
        self.project_root = Path.home()
        self.skyrl_dir = self.project_root / "SkyRL" / "skyrl-train"
        self.script_dir = Path(__file__).parent.resolve()
        self.data_dir = self.script_dir.parent / "dataset" / "cve_vulhub"  # 数据在 dataset 目录下
        self.checkpoint_dir = self.project_root / "checkpoints" / "cve_agent"
        self.vulhub_dir = self.project_root / "vulhub"

    def check_prerequisites(self) -> bool:
        """检查前置条件"""
        print("=" * 60)
        print("Checking Prerequisites")
        print("=" * 60)

        checks = []

        # SkyRL
        if self.skyrl_dir.exists():
            print(f"✓ SkyRL: {self.skyrl_dir}")
            checks.append(True)
        else:
            print(f"✗ SkyRL not found at {self.skyrl_dir}")
            checks.append(False)

        # Vulhub
        if self.vulhub_dir.exists():
            print(f"✓ Vulhub: {self.vulhub_dir}")
            checks.append(True)
        else:
            print(f"✗ Vulhub not found at {self.vulhub_dir}")
            checks.append(False)

        # Docker
        try:
            result = subprocess.run(["docker", "--version"], capture_output=True)
            if result.returncode == 0:
                print(f"✓ Docker: {result.stdout.decode().strip()}")
                checks.append(True)
            else:
                print("✗ Docker not working")
                checks.append(False)
        except:
            print("✗ Docker not found")
            checks.append(False)

        # 数据集
        train_data = self.data_dir / "train.parquet"
        if train_data.exists():
            print(f"✓ Training data: {train_data}")
            checks.append(True)
        else:
            print(f"✗ Training data not found")
            print(f"  Run: python vulhub_dataset_builder.py")
            checks.append(False)

        # 环境文件
        env_file = self.script_dir / "cve_exploit_env.py"
        if env_file.exists():
            print(f"✓ Environment: {env_file}")
            checks.append(True)
        else:
            print(f"✗ Environment file not found: {env_file}")
            checks.append(False)

        return all(checks)

    def prepare_environment(self):
        """准备训练环境"""
        print("\n" + "=" * 60)
        print("Preparing Environment")
        print("=" * 60)

        # 创建checkpoint目录
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        print(f"✓ Checkpoint dir: {self.checkpoint_dir}")

        # 构建attacker镜像
        self._build_attacker_image()

        # 复制环境文件到SkyRL目录
        files_to_copy = ["cve_exploit_env.py", "main_training.py"]
        for filename in files_to_copy:
            src = self.script_dir / filename
            if src.exists():
                dst = self.skyrl_dir / filename
                shutil.copy(src, dst)
                print(f"✓ Copied {filename}")

        # 设置PYTHONPATH
        os.environ["PYTHONPATH"] = str(self.skyrl_dir)

        # 设置Ray环境变量，允许与其他进程共享GPU
        os.environ["RAY_EXPERIMENTAL_NOSET_CUDA_VISIBLE_DEVICES"] = "1"

        # 设置UV缓存目录到/data1，避免home目录空间不足
        uv_cache_dir = "/data1/jph/.cache/uv"
        os.makedirs(uv_cache_dir, exist_ok=True)
        os.environ["UV_CACHE_DIR"] = uv_cache_dir

    def _build_attacker_image(self):
        """构建攻击者Docker镜像"""
        try:
            import docker
            client = docker.from_env()

            try:
                client.images.get("cve-attacker:latest")
                print("✓ Attacker image exists")
                return
            except:
                pass

            print("Building attacker image...")

            dockerfile = """FROM python:3.11-slim
RUN apt-get update && apt-get install -y curl wget netcat-traditional nmap dnsutils iputils-ping && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir requests
WORKDIR /attacker
CMD ["tail", "-f", "/dev/null"]
"""
            with tempfile.TemporaryDirectory() as tmpdir:
                Path(tmpdir, "Dockerfile").write_text(dockerfile)
                client.images.build(path=tmpdir, tag="cve-attacker:latest", rm=True)
                print("✓ Attacker image built")

        except Exception as e:
            print(f"Warning: Failed to build attacker image: {e}")

    def build_config(self) -> dict:
        """构建训练配置"""
        return {
            # 模型
            "model_path": "Qwen/Qwen2.5-3B-Instruct",

            # 数据
            "train_data": str(self.data_dir / "train.parquet"),

            # 训练参数 - 与之前能运行的配置一致
            "algorithm": "grpo",
            "advantage_estimator": "rloo",
            "train_batch_size": 4,
            "rollouts_per_task": 4,
            "learning_rate": 1e-6,
            "epochs": 20,

            # 系统
            "checkpoint_dir": str(self.checkpoint_dir),
        }

    def build_command(self, config: dict) -> list:
        """构建训练命令"""
        cmd = [
            "uv", "run", "--isolated", "--extra", "vllm",
            "--with", "docker",
            "--with", "requests",
            "--with", "Pillow",
            "python", "main_training.py"
        ]

        params = [
            # 数据
            f"++data.train_data=['{config['train_data']}']",
            "++data.val_data=null",

            # 算法
            f"++trainer.algorithm.name={config['algorithm']}",
            f"++trainer.algorithm.advantage_estimator={config['advantage_estimator']}",
            "++trainer.algorithm.kl_coef=0.0",
            "++trainer.algorithm.entropy_coef=0.0",
            "++trainer.algorithm.normalize_advantage=False",

            # 批次大小
            f"++trainer.train_batch_size={config['train_batch_size']}",
            f"++trainer.policy_mini_batch_size={config['train_batch_size']}",
            f"++trainer.rollout_batch_size={config['train_batch_size']}",
            f"++trainer.rollouts_per_task={config['rollouts_per_task']}",
            f"++trainer.learning_rate={config['learning_rate']}",
            f"++trainer.epochs={config['epochs']}",
            "++trainer.eval_interval=-1",

            # Checkpoint
            f"++trainer.checkpoint_dir={config['checkpoint_dir']}",
            "++trainer.save_interval=100",  # 每100步保存，减少checkpoint数量

            # 模型配置
            f"++trainer.policy.model.path={config['model_path']}",

            # LoRA配置
            "++trainer.policy.model.lora.rank=16",
            "++trainer.policy.model.lora.alpha=32",
            "++trainer.policy.model.lora.dropout=0.05",
            "++trainer.policy.model.lora.target_modules=all-linear",

            # GPU放置配置 - 单GPU共置
            "++trainer.placement.colocate_all=true",
            "++trainer.placement.policy_num_nodes=1",
            "++trainer.placement.policy_num_gpus_per_node=1",
            "++trainer.placement.ref_num_nodes=1",
            "++trainer.placement.ref_num_gpus_per_node=1",
            "++trainer.placement.critic_num_nodes=1",
            "++trainer.placement.critic_num_gpus_per_node=1",
            "++trainer.placement.reward_num_nodes=1",
            "++trainer.placement.reward_num_gpus_per_node=1",

            # Generator配置 - 使用60GB中的一部分（约50%的可用空间）
            "++generator.num_inference_engines=1",
            "++generator.inference_backend=vllm",
            "++generator.inference_engine_tensor_parallel_size=1",
            "++generator.gpu_memory_utilization=0.5",
            "+generator.engine_init_kwargs.max_model_len=4096",

            # Dispatcher
            "++dispatcher.strategy=async_pipeline",

            # 日志 - 使用本地日志
            "++logging.backend=local",

            # 关键：设置max_turns为30，允许多轮交互
            "++generator.max_turns=30",
        ]

        cmd.extend(params)
        return cmd

    def launch(self):
        """启动训练"""
        print("\n" + "=" * 60)
        print("Launching Training")
        print("=" * 60)

        config = self.build_config()

        print("\nConfiguration:")
        print(f"  Model: {config['model_path']}")
        print(f"  Algorithm: {config['algorithm']}")
        print(f"  Batch Size: {config['train_batch_size']}")
        print(f"  Epochs: {config['epochs']}")

        cmd = self.build_command(config)

        print("\n" + "=" * 60)
        print("Command:")
        print(" \\\n  ".join(cmd))
        print("=" * 60)

        os.chdir(self.skyrl_dir)

        try:
            result = subprocess.run(" ".join(cmd), shell=True, env=os.environ.copy())
            if result.returncode == 0:
                print("\n✓ Training completed!")
            else:
                print(f"\n✗ Training failed with code {result.returncode}")
        except KeyboardInterrupt:
            print("\n\nTraining interrupted")
        except Exception as e:
            print(f"\n✗ Error: {e}")


def main():
    launcher = TrainingLauncher()

    if not launcher.check_prerequisites():
        print("\n✗ Prerequisites not met")
        return 1

    launcher.prepare_environment()
    launcher.launch()
    return 0


if __name__ == "__main__":
    sys.exit(main())
