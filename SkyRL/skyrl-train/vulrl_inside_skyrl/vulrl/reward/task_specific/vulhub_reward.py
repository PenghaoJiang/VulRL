"""Vulhub specific reward computation."""

from typing import List, Dict, Any


class VulhubReward:
    """Reward computation for Vulhub tasks."""
    
    def compute(self, trajectory: List[Dict[str, Any]], task_id: str) -> float:
        """
        Compute reward for Vulhub trajectory.
        
        TODO: Implement actual reward logic:
        - Check for shell access indicators
        - Check for file read/write success
        - Check for privilege escalation
        - Parse vulnerability-specific objectives
        
        Args:
            trajectory: List of steps with observations and actions
            task_id: Vulhub task ID (e.g., "jenkins/CVE-2018-1000861")
            
        Returns:
            Reward score (currently returns 0.0 as placeholder)
        """
        # Placeholder: return 0 for now
        print(f"[VulhubReward] Computing reward for {task_id}: 0.0 (placeholder)")
        return 0.0
