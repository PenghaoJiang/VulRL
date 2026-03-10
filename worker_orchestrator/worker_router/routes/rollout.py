"""Rollout API endpoints."""

from fastapi import APIRouter, HTTPException
import uuid
import time
import json

from ..models import RolloutRequest, RolloutResponse, RolloutResult
from ..redis_client import RedisClient
from ..worker_pool import WorkerPool
from ..utils.logger import log_request, log_response
import logging

router = APIRouter()

# Will be injected by app.py
redis_client: RedisClient = None
worker_pool: WorkerPool = None
logger: logging.Logger = None


def set_dependencies(redis: RedisClient, pool: WorkerPool, log: logging.Logger):
    """Set dependencies (called from app.py)."""
    global redis_client, worker_pool, logger
    redis_client = redis
    worker_pool = pool
    logger = log


@router.post("/api/rollout/execute", response_model=RolloutResponse)
async def execute_rollout(request: RolloutRequest):
    """Execute a rollout task.
    
    Args:
        request: Rollout request
        
    Returns:
        RolloutResponse with task_id
    """
    # Log request
    log_request(logger, "execute_rollout", request)
    
    # Generate task ID
    task_id = str(uuid.uuid4())
    
    # Get available worker
    worker_id = worker_pool.get_available_worker()
    
    if not worker_id:
        # No workers available, queue task
        queued_at = time.time()
        
        # Store task metadata
        redis_client.set_task_metadata(task_id, {
            "status": "queued",
            "worker_id": None,
            "request": request.dict(),
            "queued_at": queued_at,
        })
        
        response = RolloutResponse(
            task_id=task_id,
            status="queued",
            worker_id=None,
            queued_at=queued_at,
        )
        
        # Log response
        log_response(logger, "execute_rollout", request, response)
        return response
    
    # Assign to worker
    queued_at = time.time()
    
    # Store task metadata
    redis_client.set_task_metadata(task_id, {
        "status": "running",
        "worker_id": worker_id,
        "request": request.dict(),
        "queued_at": queued_at,
        "started_at": time.time(),
    })
    
    # Push to worker queue
    redis_client.push_task(worker_id, task_id)
    
    # Update worker status
    redis_client.set_worker_status(worker_id, "busy")
    redis_client.set_task_metadata(task_id, {"current_task": task_id})
    
    response = RolloutResponse(
        task_id=task_id,
        status="running",
        worker_id=worker_id,
        queued_at=queued_at,
    )
    
    # Log response
    log_response(logger, "execute_rollout", request, response)
    return response


@router.get("/api/rollout/status/{task_id}", response_model=RolloutResult)
async def get_rollout_status(task_id: str):
    """Get rollout status and result.
    
    Args:
        task_id: Task ID
        
    Returns:
        RolloutResult
    """
    # Log request
    log_request(logger, "get_rollout_status", {"task_id": task_id})
    
    # Get task metadata
    task_meta = redis_client.get_task_metadata(task_id)
    
    if not task_meta:
        raise HTTPException(status_code=404, detail=f"Task {task_id} not found")
    
    # Build response
    result = RolloutResult(
        task_id=task_id,
        status=task_meta.get("status", "unknown"),
        worker_id=task_meta.get("worker_id"),
        queued_at=float(task_meta.get("queued_at", 0)),
        started_at=float(task_meta.get("started_at")) if task_meta.get("started_at") else None,
        completed_at=float(task_meta.get("completed_at")) if task_meta.get("completed_at") else None,
    )
    
    # If completed, get result
    if result.status == "completed":
        result_data = redis_client.get_result(task_id)
        if result_data:
            result.reward = result_data.get("reward")
            result.trajectory = result_data.get("trajectory")
            result.success = result_data.get("success")
            result.metadata = result_data.get("metadata", {})
            result.duration = result.completed_at - result.started_at if result.completed_at and result.started_at else None
    
    # If failed, get error
    if result.status == "failed":
        result.error = task_meta.get("error")
        result.error_type = task_meta.get("error_type")
    
    # Log response
    log_response(logger, "get_rollout_status", {"task_id": task_id}, result)
    return result
