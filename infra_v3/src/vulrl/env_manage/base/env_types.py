"""
Standard data types for unified security environment
"""

import json
from enum import Enum
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass, field, asdict


class ActionType(Enum):
    """Supported action types"""
    BASH = "bash"
    HTTP_REQUEST = "http_request"
    PYTHON = "python"
    UNKNOWN = "unknown"


@dataclass
class StandardAction:
    """
    Standardized action format
    
    All adapters accept this format regardless of backend
    """
    action_type: ActionType
    arguments: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StandardAction":
        """Parse action from various formats"""
        # Extract action type
        action_name = (
            data.get("tool") or 
            data.get("action") or 
            data.get("name") or
            data.get("type") or
            "unknown"
        )
        
        # Map to ActionType
        action_type_map = {
            "bash": ActionType.BASH,
            "http_request": ActionType.HTTP_REQUEST,
            "http": ActionType.HTTP_REQUEST,
            "python": ActionType.PYTHON,
        }
        action_type = action_type_map.get(action_name.lower(), ActionType.UNKNOWN)
        
        # Extract arguments
        arguments = (
            data.get("arguments") or
            data.get("args") or
            data.get("parameters") or
            data.get("params") or
            {}
        )
        
        return cls(action_type=action_type, arguments=arguments)
    
    @classmethod
    def from_json(cls, json_str: str) -> "StandardAction":
        """Parse from JSON string"""
        return cls.from_dict(json.loads(json_str))
    
    @classmethod
    def from_any(cls, action: Union[str, Dict, "StandardAction"]) -> "StandardAction":
        """Parse from any format"""
        if isinstance(action, StandardAction):
            return action
        if isinstance(action, str):
            try:
                return cls.from_json(action)
            except json.JSONDecodeError:
                # Plain text -> bash command
                return cls(
                    action_type=ActionType.BASH,
                    arguments={"command": action}
                )
        if isinstance(action, dict):
            return cls.from_dict(action)
        raise ValueError(f"Cannot parse action from type: {type(action)}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "tool": self.action_type.value,
            "arguments": self.arguments
        }
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())


@dataclass
class StandardObservation:
    """
    Standardized observation format
    
    All adapters return this format regardless of backend
    """
    text: str
    target_info: Dict[str, Any] = field(default_factory=dict)
    environment_state: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_text(self) -> str:
        """Convert to plain text (for LLM input)"""
        return self.text
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())


@dataclass
class StandardInfo:
    """
    Standardized info dict (Gymnasium-style)
    
    Contains metadata about the environment state
    """
    step: int
    max_steps: int
    task_id: str
    task_type: str
    tool_executed: Optional[str] = None
    execution_time: float = 0.0
    extra: Dict[str, Any] = field(default_factory=dict)
    final_evaluation: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())


@dataclass
class StandardEnvConfig:
    """
    Standardized environment configuration
    
    Common configuration for all environment types
    """
    task_id: str
    task_type: str  # "vulhub", "cvebench", "xbow"
    max_steps: int = 30
    timeout: int = 30
    target_host: str = "target"
    target_port: int = 80
    target_protocol: str = "http"
    evaluation_config: Dict[str, Any] = field(default_factory=dict)
    poc_info: Dict[str, Any] = field(default_factory=dict)
    backend_config: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StandardEnvConfig":
        """Create from dictionary"""
        # Filter to only valid fields
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)
    
    @classmethod
    def from_json(cls, json_str: str) -> "StandardEnvConfig":
        """Create from JSON string"""
        return cls.from_dict(json.loads(json_str))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)
    
    def to_json(self) -> str:
        """Convert to JSON string"""
        return json.dumps(self.to_dict())
