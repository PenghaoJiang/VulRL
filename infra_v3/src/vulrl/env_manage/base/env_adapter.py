"""
Base environment adapter interface

All adapters must implement this interface to ensure consistent behavior
across different data sources (Vulhub, CVE-bench, Xbow).
"""

from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any
import time

from .env_types import StandardObservation, StandardAction, StandardInfo


class BaseEnvAdapter(ABC):
    """
    Environment adapter base class
    
    Core responsibilities:
    1. Standardize reset() return values from backend environments
    2. Standardize step() return values from backend environments
    3. Convert Agent actions to backend-executable format
    
    Design principles:
    - Standardization logic is unified in the base class
    - Subclasses only implement backend-specific startup/execution logic
    - Ensures all adapters return identical formats
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Environment configuration dict (task_id, task_type, backend_config, etc.)
        """
        self.config = config
        self._current_step = 0

    # ========================================================================
    # Abstract methods (must be implemented by subclasses)
    # ========================================================================

    @abstractmethod
    def setup(self) -> None:
        """
        Start the backend environment
        
        Subclasses must implement:
        - Start Docker containers
        - Establish network connections
        - Initialize necessary resources
        """
        pass

    @abstractmethod
    def teardown(self) -> None:
        """
        Clean up the backend environment
        
        Subclasses must implement:
        - Stop containers
        - Clean up networks
        - Release resources
        """
        pass

    @abstractmethod
    def reset_backend(self) -> str:
        """
        Reset the backend environment
        
        Returns:
            Raw observation from backend (unstandardized text)
        
        Subclasses must implement:
        - Generate task description
        - Return initial observation
        """
        pass

    @abstractmethod
    def step_backend(self, action: StandardAction) -> Tuple[str, float, bool, Dict]:
        """
        Execute action in the backend environment
        
        Args:
            action: Standardized action
        
        Returns:
            (observation, reward, done, info) - raw backend return values
        
        Subclasses must implement:
        - Execute tool based on action.action_type
        - Return raw output string
        """
        pass

    @abstractmethod
    def _get_target_info(self) -> Dict[str, Any]:
        """
        Get target information (for observation)
        
        Returns:
            Target info dict (host, port, protocol, url, etc.)
        
        Subclasses must implement:
        - Return current environment's target service info
        """
        pass

    # ========================================================================
    # Standardized interface (shared by all subclasses)
    # ========================================================================

    def reset(self) -> Tuple[StandardObservation, StandardInfo]:
        """
        Standardized reset interface (Gymnasium style)
        
        Returns:
            (observation, info) - standardized return values
        
        Flow:
        1. Call subclass's reset_backend() to get raw observation
        2. Standardize to StandardObservation
        3. Build StandardInfo
        4. Return standardized results
        """
        self._current_step = 0

        # Call backend reset
        raw_observation = self.reset_backend()

        # Standardize observation
        observation = self._standardize_observation(raw_observation, is_reset=True)

        # Build standardized info
        info = StandardInfo(
            step=0,
            max_steps=self.config.get("max_steps", 30),
            task_id=self.config.get("task_id", "unknown"),
            task_type=self.config.get("task_type", "unknown")
        )

        return observation, info

    def step(self, action: StandardAction) -> Tuple[StandardObservation, float, bool, bool, StandardInfo]:
        """
        Standardized step interface (Gymnasium style)
        
        Args:
            action: Standardized action
        
        Returns:
            (observation, reward, terminated, truncated, info)
            - observation: Standardized observation
            - reward: Reward value
            - terminated: Whether episode ended due to success/failure
            - truncated: Whether episode ended due to timeout/max_steps
            - info: Standardized additional information
        
        Flow:
        1. Record execution time
        2. Call subclass's step_backend() to get raw results
        3. Standardize to StandardObservation
        4. Determine termination conditions
        5. Build StandardInfo
        6. Return standardized results
        """
        self._current_step += 1

        # Record execution time
        start_time = time.time()

        # Call backend step
        raw_observation, raw_reward, raw_done, raw_info = self.step_backend(action)

        execution_time = time.time() - start_time

        # Standardize observation
        observation = self._standardize_observation(raw_observation, is_reset=False)

        # Standardize reward (intermediate steps default to 0, final step computed by evaluator)
        reward = raw_reward

        # Determine termination conditions
        max_steps = self.config.get("max_steps", 30)
        truncated = self._current_step >= max_steps
        terminated = raw_done and not truncated

        # Build standardized info
        info = StandardInfo(
            step=self._current_step,
            max_steps=max_steps,
            task_id=self.config.get("task_id", "unknown"),
            task_type=self.config.get("task_type", "unknown"),
            tool_executed=action.action_type.value,
            execution_time=execution_time,
            extra=raw_info
        )

        return observation, reward, terminated, truncated, info

    # ========================================================================
    # Standardization helper methods (can be overridden by subclasses)
    # ========================================================================

    def _standardize_observation(self, raw_obs: str, is_reset: bool) -> StandardObservation:
        """
        Standardize observation
        
        Subclasses can override this method to customize standardization logic
        
        Args:
            raw_obs: Raw observation from backend
            is_reset: Whether this comes from reset()
        
        Returns:
            Standardized observation
        """
        return StandardObservation(
            text=raw_obs,
            target_info=self._get_target_info(),
            environment_state={
                "step": self._current_step,
                "is_reset": is_reset
            }
        )

    def is_running(self) -> bool:
        """
        Check if environment is running
        
        Returns:
            True if running, False otherwise
        
        Subclasses can override this method
        """
        return True
