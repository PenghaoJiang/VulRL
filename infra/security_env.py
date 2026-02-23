"""
统一安全环境
严格遵循 Gymnasium 接口规范

Reward 机制：使用 BLEU-based reward（通过 vulrl_inside_skyrl 的 RewardRouter），
与训练入口 vulrl_inside_skyrl/main_training.py 保持一致。
"""

import sys
import json
from typing import Dict, Any, List, Union, Optional
from pathlib import Path

# Gymnasium 导入（可选）
try:
    import gymnasium as gym
    from gymnasium import spaces
    GYM_AVAILABLE = True
except ImportError:
    GYM_AVAILABLE = False

# SkyRL 导入（可选）
try:
    from skyrl_gym.envs.base_text_env import BaseTextEnv, BaseTextEnvStepOutput
    SKYRL_AVAILABLE = True
except ImportError:
    BaseTextEnv = object
    BaseTextEnvStepOutput = None
    SKYRL_AVAILABLE = False

from .env_types import StandardObservation, StandardAction, StandardInfo, StandardEnvConfig
from .env_adapter import BaseEnvAdapter
from .vulhub_adapter import VulhubAdapter
from .ctf_adapter import CTFAdapter
from .xbow_adapter import XbowAdapter

# 导入 BLEU-based RewardRouter（从 vulrl_inside_skyrl）
_vulrl_pkg_path = str(Path(__file__).resolve().parent.parent / "SkyRL" / "skyrl-train" / "vulrl_inside_skyrl")
if _vulrl_pkg_path not in sys.path:
    sys.path.insert(0, _vulrl_pkg_path)

try:
    from vulrl.reward import RewardRouter
except ImportError:
    print("[SecurityEnv] Warning: RewardRouter not available (vulrl_inside_skyrl not found)")
    RewardRouter = None


class SecurityEnv(BaseTextEnv if SKYRL_AVAILABLE else object):
    """
    统一安全环境

    严格遵循 Gymnasium 接口：
    - reset() -> (observation, info)
    - step(action) -> (observation, reward, terminated, truncated, info)

    支持多种后端：
    - Vulhub (通过 VulhubAdapter)
    - CTF (通过 CTFAdapter)
    - Xbow (通过 XbowAdapter)
    - Custom (自定义适配器)

    特性：
    - 配置驱动，易于扩展
    - 返回值标准化
    - SkyRL 兼容
    - BLEU-based reward（通过 RewardRouter）
    """

    # 适配器注册表
    ADAPTERS = {
        "vulhub": VulhubAdapter,
        "ctf": CTFAdapter,
        "xbow": XbowAdapter,
    }

    def __init__(
        self,
        config: Optional[Union[Dict, StandardEnvConfig]] = None,
        extras: Optional[Dict] = None,
        env_config: Optional[Dict] = None,
    ):
        """
        Args:
            config: 环境配置（字典或 StandardEnvConfig）
            extras: 额外配置（用于 SkyRL 集成）
            env_config: 环境配置（兼容旧接口）
        """
        if SKYRL_AVAILABLE:
            super().__init__()

        # 解析配置
        self.config = self._parse_config(config, extras, env_config)

        # 创建适配器
        self.adapter = self._create_adapter()

        # 状态
        self.current_step = 0
        self.trajectory = []
        self.episode_result = {}

        # BLEU-based reward（与 vulrl_inside_skyrl SecurityEnv 一致）
        if RewardRouter is not None:
            task_type = self.config.task_type
            reward_config = self.config.to_dict()
            self.reward_router = RewardRouter(task_type, config=reward_config)
        else:
            self.reward_router = None

        print(f"[SecurityEnv] Created: {self.config.task_id} ({self.config.task_type})")

    def _parse_config(
        self,
        config: Optional[Union[Dict, StandardEnvConfig]],
        extras: Optional[Dict],
        env_config: Optional[Dict]
    ) -> StandardEnvConfig:
        """解析配置"""
        # 优先级: config > env_config > extras

        if isinstance(config, StandardEnvConfig):
            return config

        if isinstance(config, dict):
            return StandardEnvConfig.from_dict(config)

        if env_config:
            # 从 env_config 解析
            if isinstance(env_config, str):
                env_config = json.loads(env_config)
            return StandardEnvConfig.from_dict(env_config)

        if extras:
            # SkyRL 格式
            config_str = extras.get("env_config", "{}")
            config_dict = json.loads(config_str) if isinstance(config_str, str) else config_str

            # 解析 poc_info
            poc_info_str = extras.get("poc_info", "{}")
            poc_info = json.loads(poc_info_str) if isinstance(poc_info_str, str) else poc_info_str

            # 构建配置
            return StandardEnvConfig(
                task_id=config_dict.get("task_id", extras.get("task_id", "unknown")),
                task_type=config_dict.get("task_type", extras.get("task_type", "vulhub")),
                max_steps=extras.get("max_turns", config_dict.get("max_steps", 30)),
                timeout=config_dict.get("timeout", 30),
                target_host=config_dict.get("target_host", "target"),
                target_port=config_dict.get("target_port", 80),
                target_protocol=config_dict.get("target_protocol", "http"),
                evaluation_config=config_dict.get("evaluation_config", {}),
                poc_info=poc_info,
                backend_config=config_dict.get("backend_config", {})
            )

        raise ValueError("Must provide config, env_config, or extras")

    def _create_adapter(self) -> BaseEnvAdapter:
        """创建适配器"""
        task_type = self.config.task_type

        if task_type not in self.ADAPTERS:
            raise ValueError(
                f"Unknown task type: {task_type}. "
                f"Available: {list(self.ADAPTERS.keys())}"
            )

        # 准备适配器配置
        adapter_config = {
            "task_id": self.config.task_id,
            "task_type": self.config.task_type,
            "max_steps": self.config.max_steps,
            "timeout": self.config.timeout,
            "target_host": self.config.target_host,
            "target_port": self.config.target_port,
            "target_protocol": self.config.target_protocol,
            **self.config.backend_config  # 后端特定配置
        }

        # 创建适配器实例
        adapter_class = self.ADAPTERS[task_type]
        adapter = adapter_class(adapter_config)

        # 启动底层环境
        adapter.setup()

        return adapter

    # ========================================================================
    # Gymnasium 标准接口
    # ========================================================================

    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict] = None
    ) -> Union[tuple, str]:
        """
        重置环境（Gymnasium 风格）

        Args:
            seed: 随机种子（保留接口）
            options: 额外选项（保留接口）

        Returns:
            Gymnasium: (observation, info)
            SkyRL: str (observation text)
        """
        print(f"\n{'*'*70}")
        print(f"[RESET] Task: {self.config.task_id} ({self.config.task_type})")
        print(f"[RESET] Max steps: {self.config.max_steps}")
        print(f"{'*'*70}")

        # 重置状态
        self.current_step = 0
        self.trajectory = []
        self.episode_result = {}

        # 调用适配器的标准化 reset
        observation, info = self.adapter.reset()

        print(f"[RESET] Environment ready")
        print(f"{'*'*70}\n")

        # SkyRL 兼容：返回纯文本
        if SKYRL_AVAILABLE:
            return observation.to_text()

        # Gymnasium 标准：返回 (obs, info)
        return observation, info

    def step(
        self,
        action: Union[str, Dict, StandardAction]
    ) -> Union[tuple, "BaseTextEnvStepOutput"]:
        """
        执行一步（Gymnasium 风格）

        Args:
            action: 动作（JSON 字符串、字典或 StandardAction）

        Returns:
            Gymnasium: (observation, reward, terminated, truncated, info)
            SkyRL: BaseTextEnvStepOutput
        """
        self.current_step += 1

        print(f"\n{'='*70}")
        print(f"[STEP] {self.config.task_id} | Step {self.current_step}/{self.config.max_steps}")
        print(f"{'='*70}")

        # 标准化 action
        std_action = self._standardize_action(action)

        # 调用适配器的标准化 step
        observation, reward, terminated, truncated, info = self.adapter.step(std_action)

        # 记录轨迹（与 vulrl_inside_skyrl SecurityEnv 格式一致）
        self.trajectory.append({
            'step': self.current_step,
            'observation': observation.to_text(),
            'action': std_action,
            'reward': reward,
        })

        # 如果 episode 结束，使用 BLEU-based reward
        done = terminated or truncated
        if done and self.reward_router is not None:
            final_reward = self.reward_router.compute_reward(
                trajectory=self.trajectory,
                task_id=self.config.task_id,
            )
            reward = final_reward
            self.episode_result = {'total_reward': final_reward}
            info.final_evaluation = self.episode_result

        print(f"[STEP] Done: {done}, Reward: {reward:.2f}")
        print(f"{'='*70}\n")

        # SkyRL 兼容
        if SKYRL_AVAILABLE:
            obs_msg = {"role": "user", "content": observation.to_text()}
            return BaseTextEnvStepOutput(
                observations=[obs_msg] if not done else [],
                reward=reward,
                done=done,
                metadata=info.to_dict()
            )

        # Gymnasium 标准
        return observation, reward, terminated, truncated, info

    def close(self):
        """关闭环境"""
        if self.adapter:
            self.adapter.teardown()

    # ========================================================================
    # 辅助方法
    # ========================================================================

    def _standardize_action(self, action: Union[str, Dict, StandardAction]) -> StandardAction:
        """标准化动作"""
        if isinstance(action, StandardAction):
            return action

        if isinstance(action, str):
            try:
                action = json.loads(action)
            except json.JSONDecodeError:
                # 纯文本 -> bash 命令
                action = {"tool": "bash", "arguments": {"command": action}}

        return StandardAction.from_dict(action)

    # ========================================================================
    # 适配器注册（扩展性）
    # ========================================================================

    @classmethod
    def register_adapter(cls, task_type: str, adapter_class: type):
        """
        注册新的适配器

        用法：
            SecurityEnv.register_adapter("custom", MyCustomAdapter)
        """
        cls.ADAPTERS[task_type] = adapter_class
        print(f"[SecurityEnv] Registered adapter: {task_type} -> {adapter_class.__name__}")

    @classmethod
    def list_adapters(cls) -> list:
        """列出所有已注册的适配器"""
        return list(cls.ADAPTERS.keys())
