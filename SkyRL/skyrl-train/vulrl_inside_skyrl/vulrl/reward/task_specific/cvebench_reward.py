"""CVE-bench specific reward computation."""

from typing import List, Dict, Any


class CVEBenchReward:
    """Reward computation for CVE-bench tasks."""
    
    def compute(self, trajectory: List[Dict[str, Any]], task_id: str) -> float:
        """
        Compute reward for CVE-bench trajectory.
        
        TODO: Implement actual reward logic:
        - Check if secret file was accessed
        - Check if proof was uploaded
        - Check if unauthorized file was created
        - Parse CVE-bench objectives
        
        Args:
            trajectory: List of steps with observations and actions
            task_id: CVE-bench task ID
            
        Returns:
            Reward score (currently returns 0.0 as placeholder)
        """
        # Placeholder: return 0 for now
        print(f"[CVEBenchReward] Computing reward for {task_id}: 0.0 (placeholder)")
        return 0.0
