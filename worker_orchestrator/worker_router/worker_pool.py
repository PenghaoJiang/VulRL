"""Worker pool manager for Worker Router."""

import subprocess
import uuid
import time
import sys
import os
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
    
    def spawn_worker(self) -> Optional[str]:
        """Spawn a new worker subprocess with auto-scaling.
        
        Returns:
            Worker ID or None if at max capacity
        """
        if len(self.workers) >= self.max_workers:
            return None
        
        # Generate worker ID
        worker_id = f"auto_{str(uuid.uuid4())[:8]}"
        
        # Get paths
        worker_script = Path(__file__).parent.parent / "worker_unit" / "main.py"
        log_dir = Path(__file__).parent.parent / "logs"
        log_dir.mkdir(exist_ok=True)
        
        # Open log files with unbuffered output
        log_file = log_dir / f"worker_{worker_id}.log"
        log_handle = open(log_file, "w", buffering=1)  # Line buffered
        
        # Spawn subprocess with log output and unbuffered Python
        try:
            process = subprocess.Popen(
                [sys.executable, "-u", str(worker_script), "--worker-id", worker_id],  # -u = unbuffered
                stdout=log_handle,
                stderr=subprocess.STDOUT,  # Merge stderr to stdout
                cwd=str(Path(__file__).parent.parent),  # Run from project root
                env={**os.environ, "PYTHONUNBUFFERED": "1"},  # Force unbuffered
            )
            
            # Store process
            self.workers[worker_id] = process
            
            # Don't pre-register worker metadata in Redis
            # Worker will register itself when fully initialized and ready (takes 2-3s)
            # The wait loop in rollout.py will poll until worker appears with status="idle"
            
            return worker_id
            
        except Exception as e:
            log_handle.close()
            return None
    
    def get_available_worker(self) -> Optional[str]:
        """Get an idle worker.
        
        Returns:
            Worker ID or None if all busy
        """
        # Check for idle workers
        all_workers = self.redis_client.get_all_workers()
        for worker_id in all_workers:
            status = self.redis_client.get_worker_status(worker_id)
            if status.get("status") == "idle":
                return worker_id
        
        # No idle workers available
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
