"""Worker management API endpoints."""

from fastapi import APIRouter, HTTPException
import logging

from ..models import WorkersStatusResponse, WorkerStatus, ShutdownResponse
from ..redis_client import RedisClient
from ..worker_pool import WorkerPool
from ..utils.logger import log_request, log_response

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


@router.get("/api/workers/status", response_model=WorkersStatusResponse)
async def get_workers_status():
    """Get status of all workers.
    
    Returns:
        WorkersStatusResponse
    """
    # Log request
    log_request(logger, "get_workers_status", {})
    
    # Get all workers
    workers_data = worker_pool.get_all_workers()
    
    # Convert to WorkerStatus models
    workers = [WorkerStatus(**w) for w in workers_data]
    
    # Calculate stats
    total = len(workers)
    idle = sum(1 for w in workers if w.status == "idle")
    busy = sum(1 for w in workers if w.status == "busy")
    dead = sum(1 for w in workers if w.status == "dead")
    active = idle + busy
    queue_length = worker_pool.get_total_queue_length()
    
    response = WorkersStatusResponse(
        workers=workers,
        total=total,
        active=active,
        idle=idle,
        busy=busy,
        dead=dead,
        queue_length=queue_length,
    )
    
    # Log response
    log_response(logger, "get_workers_status", {}, response)
    return response


@router.post("/api/workers/{worker_id}/shutdown", response_model=ShutdownResponse)
async def shutdown_worker(worker_id: str):
    """Shutdown a specific worker.
    
    Args:
        worker_id: Worker ID
        
    Returns:
        ShutdownResponse
    """
    # Log request
    log_request(logger, "shutdown_worker", {"worker_id": worker_id})
    
    # Check if worker exists
    worker_status = redis_client.get_worker_status(worker_id)
    if not worker_status:
        raise HTTPException(status_code=404, detail=f"Worker {worker_id} not found")
    
    # Shutdown worker
    worker_pool.shutdown_worker(worker_id)
    
    response = ShutdownResponse(
        status="shutdown_initiated",
        worker_id=worker_id,
        message=f"Worker {worker_id} shutdown initiated",
    )
    
    # Log response
    log_response(logger, "shutdown_worker", {"worker_id": worker_id}, response)
    return response
