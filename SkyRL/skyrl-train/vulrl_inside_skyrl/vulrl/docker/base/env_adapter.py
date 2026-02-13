"""
环境适配器抽象基类
负责将不同数据源（Vulhub, CTF）转换为标准格式
"""

from abc import ABC, abstractmethod
from typing import Tuple, Dict, Any
from .env_types import StandardObservation, StandardAction, StandardInfo


class BaseEnvAdapter(ABC):
    """
    环境适配器基类

    核心职责：
    1. 将底层环境的 reset() 返回值标准化
    2. 将底层环境的 step() 返回值标准化
    3. 将 Agent 的 action 转换为底层环境可执行的格式

    设计原则：
    - 标准化逻辑在基类中统一实现
    - 子类只需实现底层环境的启动/执行逻辑
    - 保证所有适配器的返回值格式完全一致
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Args:
            config: 环境配置字典（包含 task_id, task_type, backend_config 等）
        """
        self.config = config
        self._current_step = 0

    # ========================================================================
    # 抽象方法（子类必须实现）
    # ========================================================================

    @abstractmethod
    def setup(self) -> None:
        """
        启动底层环境

        子类需要实现：
        - 启动 Docker 容器
        - 建立网络连接
        - 初始化必要的资源
        """
        pass

    @abstractmethod
    def teardown(self) -> None:
        """
        清理底层环境

        子类需要实现：
        - 停止容器
        - 清理网络
        - 释放资源
        """
        pass

    @abstractmethod
    def reset_backend(self) -> str:
        """
        重置底层环境

        Returns:
            底层环境的原始观察值（未标准化的文本）

        子类需要实现：
        - 生成任务描述
        - 返回初始观察值
        """
        pass

    @abstractmethod
    def step_backend(self, action: StandardAction) -> Tuple[str, float, bool, Dict]:
        """
        在底层环境执行动作

        Args:
            action: 标准化的动作

        Returns:
            (observation, reward, done, info) - 底层环境的原始返回值

        子类需要实现：
        - 根据 action.action_type 执行对应的工具
        - 返回原始输出字符串
        """
        pass

    @abstractmethod
    def _get_target_info(self) -> Dict[str, Any]:
        """
        获取目标信息（用于 observation）

        Returns:
            目标信息字典（host, port, protocol, url 等）

        子类需要实现：
        - 返回当前环境的目标服务信息
        """
        pass

    # ========================================================================
    # 标准化接口（所有子类共用）
    # ========================================================================

    def reset(self) -> Tuple[StandardObservation, StandardInfo]:
        """
        标准化的 reset 接口（Gymnasium 风格）

        Returns:
            (observation, info) - 标准化的返回值

        流程：
        1. 调用子类的 reset_backend() 获取原始观察值
        2. 标准化为 StandardObservation
        3. 构建 StandardInfo
        4. 返回标准化结果
        """
        self._current_step = 0

        # 调用底层 reset
        raw_observation = self.reset_backend()

        # 标准化 observation
        observation = self._standardize_observation(raw_observation, is_reset=True)

        # 构建标准化 info
        info = StandardInfo(
            step=0,
            max_steps=self.config.get("max_steps", 30),
            task_id=self.config.get("task_id", "unknown"),
            task_type=self.config.get("task_type", "unknown")
        )

        return observation, info

    def step(self, action: StandardAction) -> Tuple[StandardObservation, float, bool, bool, StandardInfo]:
        """
        标准化的 step 接口（Gymnasium 风格）

        Args:
            action: 标准化的动作

        Returns:
            (observation, reward, terminated, truncated, info)
            - observation: 标准化的观察值
            - reward: 奖励值
            - terminated: 是否因成功/失败终止
            - truncated: 是否因超时等原因截断
            - info: 标准化的额外信息

        流程：
        1. 记录执行时间
        2. 调用子类的 step_backend() 获取原始结果
        3. 标准化为 StandardObservation
        4. 判断终止条件
        5. 构建 StandardInfo
        6. 返回标准化结果
        """
        self._current_step += 1

        # 记录执行时间
        import time
        start_time = time.time()

        # 调用底层 step
        raw_observation, raw_reward, raw_done, raw_info = self.step_backend(action)

        execution_time = time.time() - start_time

        # 标准化 observation
        observation = self._standardize_observation(raw_observation, is_reset=False)

        # 标准化 reward（中间步骤默认为 0，最后一步由评估器计算）
        reward = raw_reward

        # 判断终止条件
        max_steps = self.config.get("max_steps", 30)
        truncated = self._current_step >= max_steps
        terminated = raw_done and not truncated

        # 构建标准化 info
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
    # 标准化辅助方法（子类可覆盖）
    # ========================================================================

    def _standardize_observation(self, raw_obs: str, is_reset: bool) -> StandardObservation:
        """
        标准化观察值

        子类可以覆盖此方法来自定义标准化逻辑

        Args:
            raw_obs: 底层环境的原始观察值
            is_reset: 是否来自 reset()

        Returns:
            标准化的观察值
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
        检查环境是否正在运行

        Returns:
            True if running, False otherwise

        子类可以覆盖此方法
        """
        return True
