"""
VulRL Security Environment Training Entry Point for SkyRL
Entry point for training security exploitation agents with SkyRL

This script:
1. Registers SecurityEnv to skyrl_gym
2. Starts the SkyRL training loop using BasePPOExp

Usage:
    From bash: see run_training.sh
    Direct: uv run --isolated --extra vllm python main_training.py ++trainer.epochs=1 ...
"""

import os
import ray
import hydra
from omegaconf import DictConfig
from skyrl_train.entrypoints.main_base import BasePPOExp, config_dir, validate_cfg
from skyrl_gym.envs import register


# Set Ray environment variable to allow GPU sharing
os.environ["RAY_EXPERIMENTAL_NOSET_CUDA_VISIBLE_DEVICES"] = "1"


@ray.remote(num_cpus=1)
def skyrl_entrypoint(cfg: DictConfig):
    """Ray remote task entry point for SkyRL training"""
    
    # Register SecurityEnv (supports Vulhub, CVE-bench, Xbow)
    register(
        id="vulrl.SecurityEnv",
        entry_point="vulrl.env.security_env:SecurityEnv",
    )
    
    # Start training experiment
    exp = BasePPOExp(cfg)
    exp.run()


@hydra.main(config_path=config_dir, config_name="ppo_base_config", version_base=None)
def main(cfg: DictConfig) -> None:
    """Main function - validates config and launches training"""
    
    # Validate configuration
    validate_cfg(cfg)
    
    # Initialize Ray if not already initialized
    if not ray.is_initialized():
        ray.init(
            num_gpus=1,
            include_dashboard=False,
        )
    
    # Launch training task
    ray.get(skyrl_entrypoint.remote(cfg))


if __name__ == "__main__":
    main()
