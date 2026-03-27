"""
Security Environment for VulRL.
Gymnasium-compliant interface for vulnerability exploitation training.
"""

import json
from typing import Dict, Any, Optional, Union, Tuple

# Gymnasium import (required)
import gymnasium as gym
from gymnasium import spaces

# SkyRL import (optional)
try:
    from skyrl_gym.envs.base_text_env import BaseTextEnv, BaseTextEnvStepOutput
    SKYRL_AVAILABLE = True
except ImportError:
    BaseTextEnv = object
    BaseTextEnvStepOutput = None
    SKYRL_AVAILABLE = False

from vulrl.docker1.base import BaseEnvAdapter, StandardAction, StandardObservation, StandardInfo, ActionType
from vulrl.env.env_registry import EnvRegistry
from vulrl.reward import RewardRouter


class SecurityEnv(BaseTextEnv if SKYRL_AVAILABLE else gym.Env):
    """
    Unified security environment for vulnerability exploitation.
    
    Gymnasium-compliant interface:
    - reset() -> (observation, info)
    - step(action) -> (observation, reward, terminated, truncated, info)
    
    Supports multiple backends via adapters:
    - CVE-bench (CVEBenchAdapter)
    - Vulhub (VulhubAdapter)
    - Xbow (XbowAdapter)
    """
    
    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        extras: Optional[Dict] = None,
        env_config: Optional[Dict] = None,
    ):
        """
        Initialize security environment.
        
        Args:
            config: Environment configuration
            extras: Extra configuration (for SkyRL compatibility)
            env_config: Environment config (for SkyRL compatibility)
        """
        if SKYRL_AVAILABLE:
            super().__init__()
        
        # Parse configuration
        self.config = self._parse_config(config, extras, env_config)
        
        # Create adapter using registry
        self.adapter = EnvRegistry.create(self.config)
        
        # Create reward router
        self.reward_router = RewardRouter(self.config.get('task_type', 'default'), config=self.config)
        
        # Progress tracking
        self.task_id = self.config.get('task_id', 'unknown')
        self.progress_dict = self.config.get('progress_dict', None)
        self.current_episode = 0
        self.current_step = 0
        self.max_steps = self.config.get('max_steps', 30)
        self.max_episodes = self.config.get('max_episodes', 100)
        
        # Trajectory storage (for reward computation)
        self.trajectory = []
        self.failed_to_setup = False
        
        # Setup adapter with error handling
        try:
            self.adapter.setup()
        except Exception as e:
            print(f"[SecurityEnv] WARNING: Failed to setup adapter: {e}")
            # Mark as failed but don't crash - let training continue
            self.failed_to_setup = True
        
        print(f"[SecurityEnv] Initialized: task_id={self.task_id}, task_type={self.config.get('task_type')}")

    @staticmethod
    def _normalize_config_value(value: Any) -> Any:
        """Best-effort decode of JSON-encoded nested config fields."""
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    return value
        return value

    def _merge_config_source(self, result: Dict[str, Any], source: Optional[Dict[str, Any]]) -> None:
        if not source:
            return

        normalized = {
            key: self._normalize_config_value(value)
            for key, value in source.items()
        }
        nested_env_config = normalized.pop("env_config", None)
        if isinstance(nested_env_config, dict):
            result.update(nested_env_config)
        result.update(normalized)

    def _parse_config(
        self,
        config: Optional[Dict],
        extras: Optional[Dict],
        env_config: Optional[Dict]
    ) -> Dict[str, Any]:
        """Parse configuration from multiple sources."""
        result = {}

        # Priority: config > extras > env_config
        self._merge_config_source(result, env_config)
        self._merge_config_source(result, extras)
        self._merge_config_source(result, config)

        # Set defaults
        result.setdefault('task_type', 'vulhub')
        result.setdefault('task_id', 'unknown')
        result.setdefault('max_steps', 30)
        result.setdefault('max_episodes', 100)
        
        return result

    @staticmethod
    def _info_to_dict(info: Any) -> Dict[str, Any]:
        if hasattr(info, "to_dict"):
            return info.to_dict()
        if isinstance(info, dict):
            return info
        return {}

    def _perform_reset(self) -> Tuple[StandardObservation, StandardInfo]:
        """Shared reset logic for Gymnasium reset() and SkyRL init()."""
        if self.failed_to_setup:
            raise RuntimeError(f"Environment adapter failed to setup for task {self.task_id}")

        self.current_step = 0
        self.current_episode += 1
        self.trajectory = []

        self._update_progress()

        observation, info = self.adapter.reset()

        self.trajectory.append({
            'step': self.current_step,
            'observation': observation,
            'action': None,
            'reward': 0.0
        })
        return observation, info

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict] = None
    ) -> Tuple[StandardObservation, StandardInfo]:
        """
        Reset environment to initial state.
        
        Args:
            seed: Random seed (optional)
            options: Reset options (optional)
            
        Returns:
            (observation, info) tuple
        """
        observation, info = self._perform_reset()
        
        print(f"[SecurityEnv] Reset: episode={self.current_episode}, task={self.task_id}")
        
        return observation, info

    def init(self, prompt):
        """
        SkyRL initialization hook.

        SkyRL calls init(prompt) before the first step, so we must trigger the
        real environment reset here. The dataset prompt remains authoritative;
        we only fall back to the runtime-generated prompt when the dataset
        prompt is empty.
        """
        observation, info = self._perform_reset()
        obs_text = observation.text if hasattr(observation, "text") else str(observation)
        metadata = self._info_to_dict(info)
        metadata["reset_observation"] = obs_text

        if prompt:
            return prompt, metadata
        return [{"role": "user", "content": obs_text}], metadata

    def step(
        self,
        action: Union[str, Dict, StandardAction]
    ) -> Union[Tuple, BaseTextEnvStepOutput]:
        """
        Execute action in environment.
        
        Args:
            action: Action to execute
            
        Returns:
            (observation, reward, terminated, truncated, info) tuple
        """
        if self.failed_to_setup:
            raise RuntimeError(f"Environment adapter failed to setup for task {self.task_id}")

        self.current_step += 1
        
        # Convert action to StandardAction if needed
        if isinstance(action, str):
            std_action = StandardAction(
                action_type=ActionType.BASH,
                arguments={"command": action}
            )
        elif isinstance(action, dict):
            std_action = StandardAction(**action)
        else:
            std_action = action
        
        # Execute in adapter
        observation, reward, terminated, truncated, info = self.adapter.step(std_action)
        
        # Store in trajectory
        self.trajectory.append({
            'step': self.current_step,
            'observation': observation,
            'action': std_action,
            'reward': reward
        })
        
        # Check if episode is done
        done = terminated or truncated or (self.current_step >= self.max_steps)
        
        # Compute final reward if episode is done
        if done:
            final_reward = None

            # For CTFMix bench, we directly use get_terminal_reward, otherwise use compute_reward
            if hasattr(self.adapter, "get_terminal_reward"):
                final_reward = self.adapter.get_terminal_reward()

            if final_reward is None:
                final_reward = self.reward_router.compute_reward(
                    trajectory=self.trajectory,
                    task_id=self.task_id
                )
            reward = final_reward
            print(f"[SecurityEnv] Episode done: steps={self.current_step}, reward={reward:.2f}")
        
        # Update progress
        self._update_progress()
        
        if SKYRL_AVAILABLE:
            # Extract observation text and format as list of message dicts
            obs_text = observation.text if hasattr(observation, 'text') else str(observation)
            observations = [] if done else [{"role": "user", "content": obs_text}]
            return BaseTextEnvStepOutput(
                observations=observations,
                reward=reward,
                done=done,
                metadata=self._info_to_dict(info)
            )
        else:
            return observation, reward, terminated, truncated, info
    
    def close(self) -> None:
        """Clean up environment."""
        print(f"[SecurityEnv] Closing: task={self.task_id}")
        if hasattr(self, 'adapter') and self.adapter is not None:
            self.adapter.teardown()
    
    def _update_progress(self) -> None:
        """Update shared progress dictionary."""
        if self.progress_dict is not None:
            self.progress_dict[self.task_id] = {
                'episode': self.current_episode,
                'step': self.current_step,
                'max_steps': self.max_steps,
                'completed': self.current_episode >= self.max_episodes
            }
    
    def __del__(self):
        """Cleanup on deletion."""
        try:
            self.close()
        except:
            pass
