"""
Standard types for environment adapters.
Copied from vulrl_inside_skyrl and adapted for worker_unit.
"""

from typing import Any, Dict, Optional
from dataclasses import dataclass, field
from enum import Enum


# ============================================================================
# Standardized Action Types
# ============================================================================

class ActionType(str, Enum):
    """Action type enumeration"""
    BASH = "bash"
    HTTP_REQUEST = "http_request"
    PYTHON = "python"  # Execute Python code


# ============================================================================
# Standardized Observation Structure
# ============================================================================

@dataclass
class StandardObservation:
    """
    Standardized observation value.
    All environments (Vulhub, CTF) return this unified format.
    """
    # Text observation (primary, for LLM)
    text: str

    # Structured information (optional)
    target_info: Dict[str, Any] = field(default_factory=dict)
    environment_state: Dict[str, Any] = field(default_factory=dict)

    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary (compatibility)"""
        return {
            "text": self.text,
            "target_info": self.target_info,
            "environment_state": self.environment_state,
            "metadata": self.metadata
        }

    def to_text(self) -> str:
        """Convert to plain text (for LLM)"""
        return self.text


# ============================================================================
# Standardized Action Structure
# ============================================================================

@dataclass
class StandardAction:
    """
    Standardized action.
    Agent output is uniformly converted to this format.
    """
    action_type: ActionType
    arguments: Dict[str, Any]

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            "action_type": self.action_type.value,
            "arguments": self.arguments
        }


# ============================================================================
# Standardized Info Structure
# ============================================================================

@dataclass
class StandardInfo:
    """
    Standardized info dictionary.
    Gymnasium's info return value.
    """
    # Basic information
    step: int
    max_steps: int

    # Environment state
    task_id: str
    task_type: str  # vulhub/ctf/custom

    # Execution information
    tool_executed: Optional[str] = None
    execution_time: float = 0.0

    # Evaluation information (when episode ends)
    final_evaluation: Optional[Dict] = None

    # Additional information
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
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
