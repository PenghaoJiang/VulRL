"""Reward router for task-specific reward computation."""

from typing import Dict, Any, List


class RewardRouter:
    """Routes reward computation to task-specific implementations."""
    
    def __init__(self, task_type: str):
        """
        Initialize reward router.
        
        Args:
            task_type: Type of task (cvebench, vulhub, xbow, default)
        """
        self.task_type = task_type.lower()
        self._reward_impl = self._get_reward_implementation()
    
    def _get_reward_implementation(self):
        """Get task-specific reward implementation."""
        from vulrl.reward.task_specific import CVEBenchReward, VulhubReward, XbowReward
        
        implementations = {
            'cvebench': CVEBenchReward(),
            'vulhub': VulhubReward(),
            'xbow': XbowReward(),
        }
        
        return implementations.get(self.task_type, CVEBenchReward())  # Default to CVEBench
    
    def compute_reward(
        self,
        trajectory: List[Dict[str, Any]],
        task_id: str
    ) -> float:
        """
        Compute reward for a trajectory.
        
        Args:
            trajectory: List of step dictionaries containing:
                - step: Step number
                - observation: Observation text
                - action: Action taken
                - reward: Intermediate reward
            task_id: Task identifier
            
        Returns:
            Final reward score
        """
        return self._reward_impl.compute(trajectory, task_id)


def compute_reward(
    trajectory: List[Dict[str, Any]],
    task_id: str,
    task_type: str
) -> float:
    """
    Convenience function to compute reward.
    
    Args:
        trajectory: Trajectory data
        task_id: Task identifier
        task_type: Type of task
        
    Returns:
        Reward score
    """
    router = RewardRouter(task_type)
    return router.compute_reward(trajectory, task_id)
