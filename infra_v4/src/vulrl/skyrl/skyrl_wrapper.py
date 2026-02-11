"""SkyRL integration wrapper."""

import ray
from typing import Dict, Any, Optional
from gymnasium import register


def create_skyrl_env(config: Dict[str, Any]):
    """
    Create and register SecurityEnv for SkyRL.
    
    Args:
        config: Environment configuration
        
    Returns:
        Registered environment ID
    """
    # Register environment with Gymnasium
    env_id = "VulRL-v0"
    
    try:
        register(
            id=env_id,
            entry_point="vulrl.env.security_env:SecurityEnv",
            kwargs={"config": config}
        )
    except Exception as e:
        # Already registered, ignore
        pass
    
    return env_id


@ray.remote(num_cpus=1)
def skyrl_entrypoint(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    SkyRL training entry point (runs in Ray worker).
    
    This function is called by Ray workers for distributed training.
    
    Args:
        config: Training configuration including:
            - task_id: Task identifier
            - task_type: Type of task (cvebench, vulhub, xbow)
            - max_episodes: Maximum training episodes
            - checkpoint_dir: Directory to save checkpoints
            - progress_dict: Shared progress dictionary (optional)
            
    Returns:
        Training results dictionary
    """
    try:
        # Import SkyRL (must be done inside worker)
        from skyrl.experiments import BasePPOExp
        
        # Register environment
        env_id = create_skyrl_env(config)
        
        # Create SkyRL experiment
        print(f"[SkyRL] Creating experiment for task: {config['task_id']}")
        exp = BasePPOExp(config)
        
        # Run training
        print(f"[SkyRL] Starting training...")
        result = exp.run()
        
        print(f"[SkyRL] Training complete for task: {config['task_id']}")
        return {
            'success': True,
            'task_id': config['task_id'],
            'result': result
        }
    
    except Exception as e:
        print(f"[SkyRL] Error in training: {e}")
        import traceback
        traceback.print_exc()
        return {
            'success': False,
            'task_id': config.get('task_id', 'unknown'),
            'error': str(e)
        }


def run_skyrl_training(
    task_id: str,
    task_type: str,
    base_model: str,
    checkpoint_dir: str,
    max_episodes: int = 100,
    max_steps: int = 30,
    progress_dict: Optional[Any] = None,
    **kwargs
) -> Dict[str, Any]:
    """
    High-level wrapper to run SkyRL training.
    
    Args:
        task_id: Task identifier
        task_type: Type of task (cvebench, vulhub, xbow)
        base_model: Base LLM model path
        checkpoint_dir: Directory to save checkpoints
        max_episodes: Maximum training episodes
        max_steps: Maximum steps per episode
        progress_dict: Shared progress dictionary (optional)
        **kwargs: Additional SkyRL configuration
        
    Returns:
        Training results
    """
    # Build configuration
    config = {
        'task_id': task_id,
        'task_type': task_type,
        'base_model': base_model,
        'checkpoint_dir': checkpoint_dir,
        'max_episodes': max_episodes,
        'max_steps': max_steps,
        'progress_dict': progress_dict,
        **kwargs
    }
    
    # Run training via Ray
    result_ref = skyrl_entrypoint.remote(config)
    result = ray.get(result_ref)
    
    return result
