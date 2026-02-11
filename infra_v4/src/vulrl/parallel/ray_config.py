"""Ray configuration for SkyRL integration."""

import ray
from typing import Optional, Dict, Any


def configure_ray(
    num_gpus: int = 1,
    num_cpus: Optional[int] = None,
    include_dashboard: bool = False,
    temp_dir: Optional[str] = None,
    **kwargs
) -> None:
    """
    Configure and initialize Ray for SkyRL.
    
    Args:
        num_gpus: Number of GPUs to allocate (default: 1)
        num_cpus: Number of CPUs to allocate (default: auto-detect)
        include_dashboard: Whether to include Ray dashboard
        temp_dir: Temporary directory for Ray
        **kwargs: Additional Ray.init() parameters
    """
    if ray.is_initialized():
        print("[Ray] Already initialized, skipping...")
        return
    
    ray_kwargs = {
        "num_gpus": num_gpus,
        "include_dashboard": include_dashboard,
        **kwargs
    }
    
    if num_cpus is not None:
        ray_kwargs["num_cpus"] = num_cpus
    
    if temp_dir is not None:
        ray_kwargs["_temp_dir"] = temp_dir
    
    print(f"[Ray] Initializing with: gpus={num_gpus}, dashboard={include_dashboard}")
    ray.init(**ray_kwargs)
    print("[Ray] Initialization complete")


def shutdown_ray() -> None:
    """Shutdown Ray if it's running."""
    if ray.is_initialized():
        print("[Ray] Shutting down...")
        ray.shutdown()
        print("[Ray] Shutdown complete")


def get_ray_config_for_skyrl(
    base_config: Dict[str, Any],
    task_id: str,
    checkpoint_dir: str
) -> Dict[str, Any]:
    """
    Generate SkyRL configuration with Ray settings.
    
    Args:
        base_config: Base SkyRL configuration
        task_id: Task ID for this training run
        checkpoint_dir: Directory to save checkpoints
        
    Returns:
        Updated configuration dict
    """
    config = base_config.copy()
    
    # Update task-specific settings
    config["task_id"] = task_id
    config["checkpoint_dir"] = checkpoint_dir
    
    # Ray-specific settings for SkyRL
    config["num_rollout_workers"] = config.get("num_rollout_workers", 4)
    config["num_gpus"] = config.get("num_gpus", 0.2)  # Share GPU across workers
    
    return config
