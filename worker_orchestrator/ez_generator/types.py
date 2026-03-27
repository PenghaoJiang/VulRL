"""
Type definitions for EzVulRL Generator.

Uses TypedDict for type hints without requiring Pydantic dependency.
These are just for IDE support and type checking - at runtime they're plain dicts.
"""

from typing import TypedDict, Optional, List, Dict, Any, Literal


class RolloutRequest(TypedDict):
    """Request to execute a rollout (sent as JSON dict)."""
    cve_id: str
    vulhub_path: str
    prompt: str
    max_steps: int
    timeout: int
    llm_endpoint: str
    model_name: str
    temperature: float
    max_tokens: int
    metadata: Dict[str, Any]


class RolloutResponse(TypedDict):
    """Immediate response after task submission (received as JSON dict)."""
    task_id: str
    status: Literal["queued", "running"]
    worker_id: Optional[str]
    queued_at: float
    estimated_duration: Optional[int]


class TrajectoryStep(TypedDict):
    """Single step in exploitation trajectory (received as JSON dict)."""
    step: int
    action: str
    observation: str
    reward: float
    done: bool
    metadata: Dict[str, Any]


class RolloutResult(TypedDict):
    """Complete rollout result (received as JSON dict)."""
    task_id: str
    status: Literal["queued", "running", "completed", "failed", "timeout"]
    worker_id: Optional[str]
    queued_at: float
    started_at: Optional[float]
    completed_at: Optional[float]
    duration: Optional[float]
    reward: Optional[float]
    trajectory: Optional[List[TrajectoryStep]]
    success: Optional[bool]
    metadata: Dict[str, Any]
    error: Optional[str]
    error_type: Optional[str]


class WorkerStatus(TypedDict):
    """Status of a single worker (received as JSON dict)."""
    worker_id: str
    status: Literal["idle", "busy", "dead"]
    pid: int
    started_at: float
    current_task: Optional[str]
    tasks_completed: int
    tasks_failed: int
    average_duration: Optional[float]


class WorkersStatusResponse(TypedDict):
    """Status of all workers (received as JSON dict)."""
    workers: List[WorkerStatus]
    total: int
    active: int
    idle: int
    busy: int
    dead: int
    queue_length: int
