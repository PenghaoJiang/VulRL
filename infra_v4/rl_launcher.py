#!/usr/bin/env python3
"""
VulRL Training Launcher (v4)
Entry point for parallel RL training on multiple CVEs.
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from vulrl.parallel import start_parallel_training, configure_ray
from vulrl.model import CheckpointManager


def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="VulRL Training Launcher - Train RL agent on multiple CVEs in parallel"
    )
    
    # Task configuration
    parser.add_argument(
        "--task-type",
        type=str,
        required=True,
        choices=["cvebench", "vulhub", "xbow"],
        help="Type of tasks to train on"
    )
    parser.add_argument(
        "--task-ids",
        type=str,
        required=True,
        help="Comma-separated list of task IDs to train on"
    )
    parser.add_argument(
        "--tasks-file",
        type=str,
        help="JSON file containing task list (alternative to --task-ids)"
    )
    
    # Model configuration
    parser.add_argument(
        "--base-model",
        type=str,
        default="Qwen/Qwen2.5-3B-Instruct",
        help="Base LLM model path"
    )
    parser.add_argument(
        "--checkpoint-dir",
        type=str,
        default="./checkpoints",
        help="Directory to save checkpoints"
    )
    
    # Training configuration
    parser.add_argument(
        "--max-episodes",
        type=int,
        default=100,
        help="Maximum episodes per task"
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=30,
        help="Maximum steps per episode"
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=None,
        help="Maximum parallel workers (default: CPU count)"
    )
    
    # Ray configuration
    parser.add_argument(
        "--num-gpus",
        type=int,
        default=1,
        help="Number of GPUs for Ray"
    )
    parser.add_argument(
        "--ray-dashboard",
        action="store_true",
        help="Enable Ray dashboard"
    )
    
    return parser.parse_args()


def load_tasks_from_file(tasks_file: str) -> list:
    """Load task IDs from JSON file."""
    import json
    
    with open(tasks_file, 'r') as f:
        tasks = json.load(f)
    
    # Extract task IDs
    if isinstance(tasks, list):
        if isinstance(tasks[0], dict):
            return [task['task_id'] for task in tasks]
        else:
            return tasks
    
    raise ValueError(f"Invalid tasks file format: {tasks_file}")


def main():
    """Main entry point."""
    args = parse_args()
    
    # Determine task IDs
    if args.tasks_file:
        print(f"Loading tasks from: {args.tasks_file}")
        task_ids = load_tasks_from_file(args.tasks_file)
    else:
        task_ids = [tid.strip() for tid in args.task_ids.split(',')]
    
    print(f"\n{'='*60}")
    print(f"VulRL Training Launcher v4")
    print(f"{'='*60}")
    print(f"Task type: {args.task_type}")
    print(f"Number of tasks: {len(task_ids)}")
    print(f"Tasks: {task_ids[:5]}{'...' if len(task_ids) > 5 else ''}")
    print(f"Base model: {args.base_model}")
    print(f"Checkpoint dir: {args.checkpoint_dir}")
    print(f"Max episodes: {args.max_episodes}")
    print(f"Max steps: {args.max_steps}")
    print(f"Max workers: {args.max_workers or 'auto'}")
    print(f"{'='*60}\n")
    
    # Configure Ray
    print("Initializing Ray...")
    configure_ray(
        num_gpus=args.num_gpus,
        include_dashboard=args.ray_dashboard
    )
    
    # Setup checkpoint manager
    checkpoint_manager = CheckpointManager(args.checkpoint_dir)
    
    # Build base configuration
    base_config = {
        'base_model': args.base_model,
        'checkpoint_dir': args.checkpoint_dir,
        'max_steps': args.max_steps,
        'max_episodes': args.max_episodes,
    }
    
    # Start parallel training
    results = start_parallel_training(
        task_ids=task_ids,
        task_type=args.task_type,
        base_config=base_config,
        max_workers=args.max_workers,
        max_episodes=args.max_episodes
    )
    
    # Print summary
    print(f"\n\n{'='*60}")
    print(f"Training Complete")
    print(f"{'='*60}")
    
    successful = sum(1 for r in results.values() if r.get('success', False))
    failed = len(results) - successful
    
    print(f"Total tasks: {len(results)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    
    if failed > 0:
        print(f"\nFailed tasks:")
        for task_id, result in results.items():
            if not result.get('success', False):
                print(f"  - {task_id}: {result.get('error', 'Unknown error')}")
    
    print(f"\nCheckpoints saved to: {args.checkpoint_dir}")
    print(f"{'='*60}\n")
    
    # Exit code
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
