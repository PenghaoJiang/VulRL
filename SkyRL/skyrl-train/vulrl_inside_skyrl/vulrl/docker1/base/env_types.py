"""
标准化的环境数据结构
严格遵循 Gymnasium 规范
"""

from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
import json


# ============================================================================
# 标准化的 Action 类型
# ============================================================================

class ActionType(str, Enum):
    """动作类型枚举"""
    BASH = "bash"
    HTTP_REQUEST = "http_request"


# ============================================================================
# 标准化的 Observation 结构
# ============================================================================

@dataclass
class StandardObservation:
    """
    标准化的观察值

    所有环境（Vulhub, CTF）都返回这个统一格式
    """
    # 文本观察（主要，给 LLM）
    text: str

    # 结构化信息（可选）
    target_info: Dict[str, Any] = field(default_factory=dict)
    environment_state: Dict[str, Any] = field(default_factory=dict)

    # 额外元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典（兼容性）"""
        return {
            "text": self.text,
            "target_info": self.target_info,
            "environment_state": self.environment_state,
            "metadata": self.metadata
        }

    def to_text(self) -> str:
        """转换为纯文本（用于 LLM）"""
        return self.text

    @classmethod
    def from_dict(cls, data: Dict) -> "StandardObservation":
        """从字典创建"""
        return cls(
            text=data.get("text", ""),
            target_info=data.get("target_info", {}),
            environment_state=data.get("environment_state", {}),
            metadata=data.get("metadata", {})
        )


# ============================================================================
# 标准化的 Action 结构
# ============================================================================

@dataclass
class StandardAction:
    """
    标准化的动作

    Agent 输出统一转换为这个格式
    """
    action_type: ActionType
    arguments: Dict[str, Any]

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "action_type": self.action_type.value,
            "arguments": self.arguments
        }

    @classmethod
    def from_dict(cls, action_dict: Dict) -> "StandardAction":
        """
        从字典创建（解析 Agent 输出）

        支持多种格式：
        - {"tool": "bash", "arguments": {...}}
        - {"name": "bash", "args": {...}}
        - {"action_type": "bash", "arguments": {...}}
        """
        # 提取工具名
        tool = action_dict.get("tool") or action_dict.get("name") or action_dict.get("action_type", "")

        # 提取参数
        args = action_dict.get("arguments") or action_dict.get("args") or action_dict.get("params", {})

        # 标准化 action_type
        tool_lower = tool.lower()
        if tool_lower in ["bash", "shell", "command"]:
            action_type = ActionType.BASH
        elif tool_lower in ["http_request", "http", "request", "curl"]:
            action_type = ActionType.HTTP_REQUEST
        else:
            raise ValueError(f"Unknown action type: {tool}. Available: bash, http_request")

        return cls(action_type=action_type, arguments=args)

    @classmethod
    def from_json(cls, json_str: str) -> "StandardAction":
        """从 JSON 字符串创建"""
        return cls.from_dict(json.loads(json_str))


# ============================================================================
# 标准化的 Info 结构
# ============================================================================

@dataclass
class StandardInfo:
    """
    标准化的 info 字典

    Gymnasium 的 info 返回值
    """
    # 基础信息
    step: int
    max_steps: int

    # 环境状态
    task_id: str
    task_type: str  # vulhub/ctf/custom

    # 执行信息
    tool_executed: Optional[str] = None
    execution_time: float = 0.0

    # 评估信息（episode 结束时）
    final_evaluation: Optional[Dict] = None

    # 额外信息
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典"""
        result = {
            "step": self.step,
            "max_steps": self.max_steps,
            "task_id": self.task_id,
            "task_type": self.task_type,
        }

        if self.tool_executed:
            result["tool_executed"] = self.tool_executed
        if self.execution_time > 0:
            result["execution_time"] = self.execution_time
        if self.final_evaluation:
            result["final_evaluation"] = self.final_evaluation
        if self.extra:
            result.update(self.extra)

        return result

    @classmethod
    def from_dict(cls, data: Dict) -> "StandardInfo":
        """从字典创建"""
        return cls(
            step=data.get("step", 0),
            max_steps=data.get("max_steps", 30),
            task_id=data.get("task_id", "unknown"),
            task_type=data.get("task_type", "unknown"),
            tool_executed=data.get("tool_executed"),
            execution_time=data.get("execution_time", 0.0),
            final_evaluation=data.get("final_evaluation"),
            extra={k: v for k, v in data.items()
                   if k not in ["step", "max_steps", "task_id", "task_type",
                               "tool_executed", "execution_time", "final_evaluation"]}
        )


# ============================================================================
# 标准化的环境配置
# ============================================================================

@dataclass
class StandardEnvConfig:
    """
    标准化的环境配置

    所有环境类型都使用这个统一配置
    """
    # 任务标识
    task_id: str
    task_type: str  # vulhub/ctf/custom

    # 环境设置
    max_steps: int = 30
    timeout: int = 30

    # 目标信息
    target_host: str = "target"
    target_port: int = 80
    target_protocol: str = "http"

    # 评估设置
    evaluation_config: Dict[str, Any] = field(default_factory=dict)

    # PoC 信息（用于奖励计算）
    poc_info: Dict[str, Any] = field(default_factory=dict)

    # 底层环境配置（特定于环境类型）
    backend_config: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "task_id": self.task_id,
            "task_type": self.task_type,
            "max_steps": self.max_steps,
            "timeout": self.timeout,
            "target_host": self.target_host,
            "target_port": self.target_port,
            "target_protocol": self.target_protocol,
            "evaluation_config": self.evaluation_config,
            "poc_info": self.poc_info,
            "backend_config": self.backend_config,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "StandardEnvConfig":
        """从字典创建"""
        return cls(
            task_id=data.get("task_id", "unknown"),
            task_type=data.get("task_type", "vulhub"),
            max_steps=data.get("max_steps", 30),
            timeout=data.get("timeout", 30),
            target_host=data.get("target_host", "target"),
            target_port=data.get("target_port", 80),
            target_protocol=data.get("target_protocol", "http"),
            evaluation_config=data.get("evaluation_config", {}),
            poc_info=data.get("poc_info", {}),
            backend_config=data.get("backend_config", {}),
        )

    @classmethod
    def from_json(cls, json_str: str) -> "StandardEnvConfig":
        """从 JSON 字符串创建"""
        return cls.from_dict(json.loads(json_str))

    def to_json(self) -> str:
        """转换为 JSON 字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
