"""Worker pool manager for Worker Router."""

import subprocess
import uuid
import time
import sys
from typing import Optional, List, Dict
from pathlib import Path

from .redis_client import RedisClient


class WorkerPool:
    """Manages worker subprocesses."""
    
    def __init__(self, redis_client: RedisClient, max_workers: int = 10):
        """Initialize worker pool.
        
        Args:
            redis_client: Redis client instance
            max_workers: Maximum number of workers
        """
        self.redis_client = redis_client
        self.max_workers = max_workers
        self.workers: Dict[str, subprocess.Popen] = {}
    
    def spawn_worker(self) -> str:
        """Spawn a new worker subprocess.
        
        Returns:
            Worker ID
        """
        if len(self.workers) >= self.max_workers:
            return None
        
        # Generate worker ID
        worker_id = str(uuid.uuid4())[:8]
        
        # Get path to worker_unit main.py
        worker_script = Path(__file__).parent.parent / "worker_unit" / "main.py"
        
        # Spawn subprocess
        process = subprocess.Popen(
            [sys.executable, str(worker_script), "--worker-id", worker_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        
        # Store process
        self.workers[worker_id] = process
        
        # Initialize worker metadata in Redis
        self.redis_client.set_worker_metadata(worker_id, {
            "status": "idle",
            "pid": process.pid,
            "started_at": time.time(),
            "current_task": None,
            "tasks_completed": 0,
            "tasks_failed": 0,
        })
        
        return worker_id
    
    def get_available_worker(self) -> Optional[str]:
        """Get an idle worker or spawn a new one.
        
        Returns:
            Worker ID or None if all busy and at max capacity
        """
        # Check for idle workers
        all_workers = self.redis_client.get_all_workers()
        for worker_id in all_workers:
            status = self.redis_client.get_worker_status(worker_id)
            if status.get("status") == "idle":
                return worker_id
        
        # Spawn new worker if under limit
        if len(self.workers) < self.max_workers:
            return self.spawn_worker()
        
        return None
    
    def get_all_workers(self) -> List[Dict]:
        """Get status of all workers.
        
        Returns:
            List of worker status dicts
        """
        workers = []
        all_worker_ids = self.redis_client.get_all_workers()
        
        for worker_id in all_worker_ids:
            status = self.redis_client.get_worker_status(worker_id)
            if status:
                workers.append(status)
        
        return workers
    
    def shutdown_worker(self, worker_id: str):
        """Shutdown a specific worker.
        
        Args:
            worker_id: Worker ID
        """
        # Mark as dead in Redis
        self.redis_client.set_worker_status(worker_id, "dead")
        
        # Terminate process if exists
        if worker_id in self.workers:
            process = self.workers[worker_id]
            process.terminate()
            process.wait(timeout=5)
            del self.workers[worker_id]
    
    def shutdown_all(self):
        """Shutdown all workers."""
        worker_ids = list(self.workers.keys())
        for worker_id in worker_ids:
            self.shutdown_worker(worker_id)
    
    def get_total_queue_length(self) -> int:
        """Get total number of queued tasks across all workers.
        
        Returns:
            Total queue length
        """
        total = 0
        all_workers = self.redis_client.get_all_workers()
        for worker_id in all_workers:
            total += self.redis_client.get_queue_length(worker_id)
        return total
