"""Pydantic models for Worker Router API."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal


# ============================================
# Worker Router API Models
# ============================================

class RolloutRequest(BaseModel):
    """Request to execute a rollout."""
    cve_id: str
    vulhub_path: str
    prompt: str
    max_steps: int = 20
    timeout: int = 1800
    llm_endpoint: str
    model_name: str
    temperature: float = 0.7
    max_tokens: int = 512
    metadata: Dict[str, Any] = {}


class RolloutResponse(BaseModel):
    """Immediate response after task submission."""
    task_id: str
    status: Literal["queued", "running"]
    worker_id: Optional[str] = None
    queued_at: float
    estimated_duration: Optional[int] = None


class TrajectoryStep(BaseModel):
    """Single step in exploitation trajectory."""
    step: int
    action: str
    observation: str
    reward: float
    done: bool
    metadata: Dict[str, Any]


class RolloutResult(BaseModel):
    """Complete rollout result."""
    task_id: str
    status: Literal["queued", "running", "completed", "failed", "timeout"]
    worker_id: Optional[str] = None
    queued_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration: Optional[float] = None
    reward: Optional[float] = None
    trajectory: Optional[List[TrajectoryStep]] = None
    success: Optional[bool] = None
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None
    error_type: Optional[str] = None


class WorkerStatus(BaseModel):
    """Status of a single worker."""
    worker_id: str
    status: Literal["idle", "busy", "dead"]
    pid: int
    started_at: float
    current_task: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    average_duration: Optional[float] = None


class WorkersStatusResponse(BaseModel):
    """Status of all workers."""
    workers: List[WorkerStatus]
    total: int
    active: int
    idle: int
    busy: int
    dead: int
    queue_length: int


class ShutdownResponse(BaseModel):
    """Response for worker shutdown."""
    status: str
    worker_id: str
    message: str


# ============================================
# LLM API Models (OpenAI-compatible)
# ============================================

class Message(BaseModel):
    """Single message in conversation."""
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request."""
    model: str
    messages: List[Message]
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 1.0
    top_k: int = -1
    repetition_penalty: float = 1.0
    stop: Optional[List[str]] = None
    stream: bool = False


class Choice(BaseModel):
    """Single completion choice."""
    index: int
    message: Message
    finish_reason: Literal["stop", "length", "abort"]
    logprobs: Optional[Dict[str, Any]] = None


class Usage(BaseModel):
    """Token usage statistics."""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage


# ============================================
# Error Models
# ============================================

class ErrorInfo(BaseModel):
    """Error information."""
    message: str
    type: str
    code: str
    details: Dict[str, Any] = {}


class ErrorResponse(BaseModel):
    """Error response."""
    error: ErrorInfo
