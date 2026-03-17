"""
Reward calculator for VulRL worker unit.
Delegates to RewardRouter for task-specific reward computation.
"""

from typing import List, Dict, Any, Optional
from worker_unit.reward.reward_router import RewardRouter


class RewardCalculator:
    """
    Calculate rewards for VulRL rollouts.
    
    Uses RewardRouter to delegate to task-specific implementations
    (VulhubReward, CVEBenchReward, XbowReward).
    """
    
    def __init__(self, task_type: str = "vulhub", config: Optional[Dict[str, Any]] = None):
        """
        Initialize reward calculator.
        
        Args:
            task_type: Type of task (vulhub, cvebench, xbow)
            config: Configuration dict (e.g., dataset_path for VulhubReward)
        """
        self.task_type = task_type
        self.config = config or {}
        self.router = RewardRouter(task_type, config=self.config)
    
    def compute_step_reward(
        self,
        action: str,
        observation: str,
        step: int,
        metadata: Dict[str, Any]
    ) -> float:
        """
        Compute reward for a single step.
        
        Args:
            action: Action taken by agent
            observation: Observation received
            step: Current step number
            metadata: Additional metadata
            
        Returns:
            Reward value (currently 0.0 - all reward computation is end-of-episode)
        """
        return 0.0
    
    def compute_episode_reward(
        self,
        trajectory: List[Dict[str, Any]],
        task_id: str
    ) -> float:
        """
        Compute final reward for entire episode.
        
        Delegates to RewardRouter which routes to task-specific implementations.
        
        Args:
            trajectory: List of trajectory steps (dicts with 'action', 'observation', etc.)
            task_id: Task identifier (e.g., vulhub_path like "apache/CVE-2021-41773")
            
        Returns:
            Final episode reward score
        """
        return self.router.compute_reward(trajectory, task_id)
