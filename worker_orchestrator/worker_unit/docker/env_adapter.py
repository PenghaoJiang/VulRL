"""
Environment adapter abstract base class.
Responsible for converting different data sources (Vulhub, CTF) to standard format.
"""

from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any
from .env_types import StandardObservation, StandardAction, StandardInfo


class BaseEnvAdapter(ABC):
    """
    Environment adapter base class.

    Core responsibilities:
    1. Standardize reset() return values from underlying environments
    2. Standardize step() return values from underlying environments
    3. Convert Agent actions to executable format for underlying environments

    Design principles:
    - Standardization logic is uniformly implemented in the base class
    - Subclasses only need to implement startup/execution logic for underlying environments
    - Ensure all adapters return values in exactly the same format
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: Environment configuration dictionary (contains task_id, task_type, backend_config, etc.)
        """
        self.config = config
        self._current_step = 0

    # ========================================================================
    # Abstract methods (subclasses must implement)
    # ========================================================================

    @abstractmethod
    def setup(self) -> None:
        """
        Start the underlying environment.

        Subclasses need to implement:
        - Start Docker containers
        - Establish network connections
        - Initialize necessary resources
        """
        pass

    @abstractmethod
    def teardown(self) -> None:
        """
        Clean up the underlying environment.

        Subclasses need to implement:
        - Stop containers
        - Clean up network
        - Release resources
        """
        pass

    @abstractmethod
    def reset_backend(self) -> str:
        """
        Reset the underlying environment.

        Returns:
            Raw observation from underlying environment (unstandardized text)

        Subclasses need to implement:
        - Generate task description
        - Return initial observation
        """
        pass

    @abstractmethod
    def step_backend(self, action: StandardAction) -> Tuple[str, float, bool, Dict]:
        """
        Execute action in the underlying environment.

        Args:
            action: Standardized action

        Returns:
            (observation, reward, done, info) - raw return values from underlying environment

        Subclasses need to implement:
        - Execute corresponding tool based on action.action_type
        - Return raw output string
        """
        pass

    @abstractmethod
    def _get_target_info(self) -> Dict[str, Any]:
        """
        Get target information (for observation).

        Returns:
            Target information dictionary (host, port, protocol, url, etc.)

        Subclasses need to implement:
        - Return current environment's target service information
        """
        pass

    # ========================================================================
    # Standardized interface (shared by all subclasses)
    # ========================================================================

    def reset(self) -> Tuple[StandardObservation, StandardInfo]:
        """
        Standardized reset interface (Gymnasium style).

        Returns:
            (observation, info) - standardized return values

        Flow:
        1. Call subclass's reset_backend() to get raw observation
        2. Standardize to StandardObservation
        3. Build StandardInfo
        4. Return standardized result
        """
        self._current_step = 0

        # Call underlying reset
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
        Standardized step interface (Gymnasium style).

        Args:
            action: Standardized action

        Returns:
            (observation, reward, terminated, truncated, info)
            - observation: Standardized observation
            - reward: Reward value
            - terminated: Whether terminated due to success/failure
            - truncated: Whether truncated due to timeout, etc.
            - info: Standardized additional information

        Flow:
        1. Record execution time
        2. Call subclass's step_backend() to get raw result
        3. Standardize to StandardObservation
        4. Determine termination conditions
        5. Build StandardInfo
        6. Return standardized result
        """
        self._current_step += 1

        # Record execution time
        import time
        start_time = time.time()

        # Call underlying step
        raw_observation, raw_reward, raw_done, raw_info = self.step_backend(action)

        execution_time = time.time() - start_time

        # Standardize observation
        observation = self._standardize_observation(raw_observation, is_reset=False)

        # Standardize reward (intermediate steps default to 0, final step calculated by evaluator)
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
    # Standardization helper methods (subclasses can override)
    # ========================================================================

    def _standardize_observation(self, raw_obs: str, is_reset: bool) -> StandardObservation:
        """
        Standardize observation.

        Subclasses can override this method to customize standardization logic.

        Args:
            raw_obs: Raw observation from underlying environment
            is_reset: Whether from reset()

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
        Check if environment is running.

        Returns:
            True if running, False otherwise

        Subclasses can override this method
        """
        return True
