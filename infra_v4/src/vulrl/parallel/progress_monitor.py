"""Progress monitoring with multiple tqdm bars for parallel training."""

from typing import Dict, List, Optional
from tqdm import tqdm
from multiprocessing import Manager
import time


class ProgressMonitor:
    """Manages multiple progress bars for parallel training tasks."""
    
    def __init__(self, task_ids: List[str], max_episodes: int = 100):
        """
        Initialize progress monitor.
        
        Args:
            task_ids: List of task IDs to monitor
            max_episodes: Maximum number of episodes per task
        """
        self.task_ids = task_ids
        self.max_episodes = max_episodes
        self.bars: Dict[str, tqdm] = {}
        self.manager = Manager()
        self.progress_dict = self.manager.dict()
        self.start_time = None
        
        # Initialize progress dict
        for task_id in task_ids:
            self.progress_dict[task_id] = {
                'episode': 0,
                'step': 0,
                'max_steps': 30,
                'completed': False
            }
    
    def create_bars(self) -> None:
        """Create progress bars for all tasks."""
        print(f"\nTraining {len(self.task_ids)} tasks in parallel...\n")
        
        for idx, task_id in enumerate(self.task_ids):
            # Truncate task_id for display
            display_id = task_id[:20].ljust(20)
            
            bar = tqdm(
                total=100,  # Percentage
                desc=f"[{display_id}]",
                position=idx,
                leave=True,
                bar_format='{desc} Ep {postfix[episode]:>3}/{postfix[max_ep]:<3} | Step {postfix[step]:>2}/{postfix[max_steps]:<2} ({percentage:3.0f}%) |{bar}|'
            )
            
            bar.set_postfix({
                'episode': 0,
                'max_ep': self.max_episodes,
                'step': 0,
                'max_steps': 30
            })
            
            self.bars[task_id] = bar
        
        self.start_time = time.time()
    
    def update_bars(self) -> None:
        """Update all progress bars based on progress_dict."""
        for task_id, progress_info in self.progress_dict.items():
            if task_id not in self.bars:
                continue
            
            bar = self.bars[task_id]
            episode = progress_info['episode']
            step = progress_info['step']
            max_steps = progress_info['max_steps']
            
            # Calculate percentage (step within current episode)
            percentage = int((step / max_steps) * 100) if max_steps > 0 else 0
            
            # Update bar
            bar.n = percentage
            bar.set_postfix({
                'episode': episode,
                'max_ep': self.max_episodes,
                'step': step,
                'max_steps': max_steps
            })
            bar.refresh()
    
    def close_bars(self) -> None:
        """Close all progress bars."""
        for bar in self.bars.values():
            bar.close()
        
        if self.start_time is not None:
            elapsed = time.time() - self.start_time
            print(f"\n\nTotal training time: {elapsed/60:.1f} minutes")
        
        print("All tasks completed!")
    
    def get_progress_dict(self):
        """Get the shared progress dictionary for worker processes."""
        return self.progress_dict
    
    def print_summary(self) -> None:
        """Print summary statistics."""
        total_episodes = sum(
            info['episode'] 
            for info in self.progress_dict.values()
        )
        avg_episode = total_episodes / len(self.task_ids) if self.task_ids else 0
        
        completed_count = sum(
            1 for info in self.progress_dict.values() 
            if info.get('completed', False)
        )
        
        print(f"\n{'=' * 60}")
        print(f"Training Summary")
        print(f"{'=' * 60}")
        print(f"Total tasks: {len(self.task_ids)}")
        print(f"Completed: {completed_count}/{len(self.task_ids)}")
        print(f"Average episodes: {avg_episode:.1f}/{self.max_episodes}")
        print(f"{'=' * 60}\n")


def format_bar_description(
    task_id: str,
    episode: int,
    step: int,
    max_steps: int
) -> str:
    """
    Format progress bar description.
    
    Args:
        task_id: Task identifier
        episode: Current episode number
        step: Current step within episode
        max_steps: Maximum steps per episode
        
    Returns:
        Formatted description string
    """
    display_id = task_id[:20].ljust(20)
    percentage = int((step / max_steps) * 100) if max_steps > 0 else 0
    return f"[{display_id}] Ep {episode:>3} | Step {step:>2}/{max_steps:<2} ({percentage:3d}%)"
