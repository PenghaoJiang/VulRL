"""
[DEPRECATED] 此文件已弃用。
实际训练入口已迁移至: vulrl_inside_skyrl/main_training.py
该入口注册 vulrl.env.security_env:SecurityEnv（新版），使用 BLEU-based reward。

---
Unified Security Environment Training Entry Point for SkyRL (原始说明)
用法: uv run --isolated --extra vllm python main_training.py

这是SkyRL训练的入口点，负责：
1. 注册统一安全环境到skyrl_gym（支持 Vulhub 和 CTF）
2. 启动训练循环

支持的环境类型：
- Vulhub: CVE 漏洞利用环境
- CTF: CTF 挑战环境（包括 CVE-bench）
"""

import os
import ray
import hydra
from omegaconf import DictConfig
from skyrl_train.entrypoints.main_base import BasePPOExp, config_dir, validate_cfg
from skyrl_gym.envs import register


# 设置环境变量
os.environ["RAY_EXPERIMENTAL_NOSET_CUDA_VISIBLE_DEVICES"] = "1"
os.environ["CUDA_VISIBLE_DEVICES"] = "0"


@ray.remote(num_cpus=1)
def skyrl_entrypoint(cfg: DictConfig):
    """Ray远程任务入口点"""

    # 注册统一安全环境（支持 Vulhub 和 CTF）
    register(
        id="security_env.SecurityEnv",
        entry_point="security_env:SecurityEnv",
    )

    # 向后兼容：也注册旧的环境名
    register(
        id="cve_exploit_env.CVEExploitEnv",
        entry_point="security_env:SecurityEnv",
    )

    # 启动训练
    exp = BasePPOExp(cfg)
    exp.run()


@hydra.main(config_path=config_dir, config_name="ppo_base_config", version_base=None)
def main(cfg: DictConfig) -> None:
    """主函数"""
    # 验证配置
    validate_cfg(cfg)

    # 手动初始化Ray，强制指定GPU资源
    # 使用/data1目录下的临时目录，因为home目录空间不足
    ray_temp_dir = "/data1/jph/ray_tmp"
    os.makedirs(ray_temp_dir, exist_ok=True)

    if not ray.is_initialized():
        ray.init(
            num_gpus=1,
            include_dashboard=False,
            _temp_dir=ray_temp_dir,
        )

    # 启动训练任务
    ray.get(skyrl_entrypoint.remote(cfg))


if __name__ == "__main__":
    main()
