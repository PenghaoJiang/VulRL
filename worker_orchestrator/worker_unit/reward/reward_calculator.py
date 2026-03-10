"""
Reward calculator for VulRL worker unit.
Currently returns 0.0 for all steps (TODO: implement actual reward logic).
"""

from typing import List, Dict, Any


class RewardCalculator:
    """
    Calculate rewards for VulRL rollouts.
    
    TODO: Implement actual reward computation logic based on:
    - Command execution success
    - Target system compromise indicators
    - Vulnerability exploitation evidence
    """
    
    def __init__(self):
        pass
    
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
            Reward value (currently 0.0)
            
        TODO: Implement actual logic:
        - Parse command output for success indicators
        - Check for vulnerability exploitation evidence
        - Detect system compromise
        """
        # TODO: Implement reward logic
        return 0.0
    
    def compute_episode_reward(
        self,
        trajectory: List[Dict[str, Any]],
        task_id: str
    ) -> float:
        """
        Compute final reward for entire episode.
        
        Args:
            trajectory: List of trajectory steps
            task_id: Task identifier
            
        Returns:
            Final episode reward (currently 0.0)
            
        TODO: Implement actual logic:
        - Analyze complete trajectory
        - Check for successful exploitation
        - Evaluate quality of PoC
        """
        # TODO: Implement episode reward logic
        return 0.0
