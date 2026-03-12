"""
Security Environment for VulRL Worker Unit.
Simplified Gymnasium-compliant interface for vulnerability exploitation.
"""

from typing import Dict, Any, Optional, Tuple
from pathlib import Path

from worker_unit.docker import VulhubAdapter, StandardAction, ActionType


class SecurityEnv:
    """
    Unified security environment for vulnerability exploitation.
    
    Gymnasium-compliant interface:
    - reset() -> (observation, info)
    - step(action) -> (observation, reward, terminated, truncated, info)
    
    Uses VulhubAdapter to manage Docker environments.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize security environment.
        
        Args:
            config: Environment configuration
        """
        self.config = config or {}
        
        # Create adapter (currently only supports Vulhub)
        self.adapter = VulhubAdapter(self.config)
        
        # Progress tracking
        self.task_id = self.config.get('task_id', 'unknown')
        self.current_step = 0
        self.max_steps = self.config.get('max_steps', 30)
        
        # Trajectory storage (for reward computation)
        self.trajectory = []
        
        # Setup adapter with error handling
        try:
            self.adapter.setup()
            self.failed_to_setup = False
        except RuntimeError as e:
            print(f"[SecurityEnv] WARNING: Failed to setup adapter: {e}")
            self.failed_to_setup = True
            raise
        
        print(f"[SecurityEnv] Initialized: task_id={self.task_id}, task_type={self.config.get('task_type')}")
    
    def reset(self, seed: Optional[int] = None, options: Optional[Dict] = None) -> Tuple[str, Dict]:
        """
        Reset environment to initial state.
        
        Args:
            seed: Random seed (optional)
            options: Reset options (optional)
            
        Returns:
            (observation, info) tuple
        """
        # Reset counters
        self.current_step = 0
        self.trajectory = []
        
        # Reset adapter
        observation, info = self.adapter.reset()
        
        # Extract observation text
        obs_text = observation.text if hasattr(observation, 'text') else str(observation)
        
        # Store in trajectory
        self.trajectory.append({
            'step': self.current_step,
            'observation': obs_text,
            'action': None,
            'reward': 0.0
        })
        
        print(f"[SecurityEnv] Reset: task={self.task_id}")
        
        return obs_text, info.to_dict()
    
    def step(self, action: str) -> Tuple[str, float, bool, bool, Dict]:
        """
        Execute action in environment.
        
        Args:
            action: Action to execute (string)
            
        Returns:
            (observation, reward, terminated, truncated, info) tuple
        """
        self.current_step += 1
        
        # Convert string action to StandardAction
        # For now, assume all string actions are bash commands
        std_action = StandardAction(
            action_type=ActionType.BASH,
            arguments={"command": action}
        )
        
        # Execute in adapter
        observation, reward, terminated, truncated, info = self.adapter.step(std_action)
        
        # Extract observation text
        obs_text = observation.text if hasattr(observation, 'text') else str(observation)
        
        # Store in trajectory
        self.trajectory.append({
            'step': self.current_step,
            'observation': obs_text,
            'action': action,
            'reward': reward
        })
        
        # Check if episode is done
        done = terminated or truncated
        
        if done:
            print(f"[SecurityEnv] Episode done: steps={self.current_step}, reward={reward:.2f}")
        
        return obs_text, reward, terminated, truncated, info.to_dict()
    
    def close(self) -> None:
        """Clean up environment."""
        print(f"[SecurityEnv] Closing: task={self.task_id}")
        if hasattr(self, 'adapter') and self.adapter is not None:
            self.adapter.teardown()
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.close()
        except:
            pass
