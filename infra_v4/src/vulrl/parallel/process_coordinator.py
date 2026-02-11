"""Process-level parallelization for training multiple CVEs."""

from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
import time
import traceback

from .progress_monitor import ProgressMonitor
from .ray_config import configure_ray, shutdown_ray


def start_parallel_training(
    task_ids: List[str],
    task_type: str,
    base_config: Dict[str, Any],
    max_workers: Optional[int] = None,
    max_episodes: int = 100
) -> Dict[str, Any]:
    """
    Start parallel training for multiple tasks using ProcessPoolExecutor.
    
    Args:
        task_ids: List of task IDs to train on
        task_type: Type of tasks (cvebench, vulhub, xbow)
        base_config: Base configuration for training
        max_workers: Maximum number of parallel workers (default: CPU count)
        max_episodes: Maximum episodes per task
        
    Returns:
        Dictionary with training results for each task
    """
    print(f"\n{'='*60}")
    print(f"Starting Parallel Training")
    print(f"{'='*60}")
    print(f"Task type: {task_type}")
    print(f"Number of tasks: {len(task_ids)}")
    print(f"Max workers: {max_workers or 'auto'}")
    print(f"Max episodes: {max_episodes}")
    print(f"{'='*60}\n")
    
    # Create progress monitor
    monitor = ProgressMonitor(task_ids, max_episodes)
    monitor.create_bars()
    progress_dict = monitor.get_progress_dict()
    
    # Training results
    results = {}
    
    try:
        # Start parallel training
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_task = {}
            for task_id in task_ids:
                # Create task-specific config
                task_config = base_config.copy()
                task_config['task_id'] = task_id
                task_config['task_type'] = task_type
                task_config['max_episodes'] = max_episodes
                
                future = executor.submit(
                    train_single_task,
                    task_id,
                    task_config,
                    progress_dict
                )
                future_to_task[future] = task_id
            
            # Monitor progress and collect results
            for future in as_completed(future_to_task):
                task_id = future_to_task[future]
                
                try:
                    result = future.result()
                    results[task_id] = result
                    print(f"\n[✓] Task completed: {task_id}")
                    
                    # Mark as completed in progress
                    if task_id in progress_dict:
                        info = dict(progress_dict[task_id])
                        info['completed'] = True
                        progress_dict[task_id] = info
                    
                except Exception as e:
                    print(f"\n[✗] Task failed: {task_id}")
                    print(f"Error: {e}")
                    traceback.print_exc()
                    results[task_id] = {'error': str(e), 'success': False}
                
                # Update progress bars
                monitor.update_bars()
    
    finally:
        # Clean up
        monitor.close_bars()
        monitor.print_summary()
    
    return results


def train_single_task(
    task_id: str,
    config: Dict[str, Any],
    progress_dict: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Train on a single task (called by worker process).
    
    Args:
        task_id: Task identifier
        config: Training configuration
        progress_dict: Shared progress dictionary (optional)
        
    Returns:
        Training results dictionary
    """
    import os
    from vulrl.skyrl import skyrl_entrypoint
    
    print(f"\n[Process {os.getpid()}] Starting training: {task_id}")
    
    try:
        # Initialize Ray for this process
        configure_ray(
            num_gpus=config.get('num_gpus', 0.2),
            include_dashboard=False
        )
        
        # Add progress dict to config
        if progress_dict is not None:
            config['progress_dict'] = progress_dict
        
        # Run SkyRL training
        result = skyrl_entrypoint(config)
        
        print(f"\n[Process {os.getpid()}] Training complete: {task_id}")
        return {
            'task_id': task_id,
            'success': True,
            'result': result
        }
    
    except Exception as e:
        print(f"\n[Process {os.getpid()}] Training failed: {task_id}")
        traceback.print_exc()
        return {
            'task_id': task_id,
            'success': False,
            'error': str(e)
        }
    
    finally:
        # Shutdown Ray for this process
        shutdown_ray()
