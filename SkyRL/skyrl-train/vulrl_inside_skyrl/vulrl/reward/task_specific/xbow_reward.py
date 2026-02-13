"""Xbow specific reward computation."""

from typing import List, Dict, Any


class XbowReward:
    """Reward computation for Xbow tasks."""
    
    def compute(self, trajectory: List[Dict[str, Any]], task_id: str) -> float:
        """
        Compute reward for Xbow trajectory.
        
        TODO: Implement actual reward logic:
        - Check for flag capture (CTF-style)
        - Parse flag format (e.g., "flag{...}")
        - Check for challenge completion indicators
        - Verify exploit success
        
        Args:
            trajectory: List of steps with observations and actions
            task_id: Xbow task ID
            
        Returns:
            Reward score (currently returns 0.0 as placeholder)
        """
        # Placeholder: return 0 for now
        print(f"[XbowReward] Computing reward for {task_id}: 0.0 (placeholder)")
        return 0.0
