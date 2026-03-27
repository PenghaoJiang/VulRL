"""Worker Unit main entry point - Redis polling."""

import argparse
import asyncio
import time
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from worker_router.redis_client import RedisClient
from worker_router.config import Config
from worker_router.models import RolloutRequest
from worker_unit.rollout_executor import RolloutExecutor


class WorkerUnit:
    """Worker unit that executes rollouts."""
    
    def __init__(self, worker_id: str, redis_client: RedisClient):
        """Initialize worker unit.
        
        Args:
            worker_id: Worker ID
            redis_client: Redis client
        """
        self.worker_id = worker_id
        self.redis_client = redis_client
        self.executor = RolloutExecutor()
        self.running = True
    
    async def run(self):
        """Main worker loop: poll Redis queue and execute tasks."""
        print(f"[Worker {self.worker_id}] Started")
        
        # Register worker in Redis
        import os
        import time
        self.redis_client.set_worker_metadata(self.worker_id, {
            "status": "idle",
            "pid": os.getpid(),
            "started_at": time.time(),
            "current_task": None,
            "tasks_completed": 0,
            "tasks_failed": 0,
        })
        print(f"[Worker {self.worker_id}] Registered in Redis")
        print(f"[Worker {self.worker_id}] Ready to process tasks")
        
        while self.running:
            # Poll queue for task
            task_id = self.redis_client.pop_task(self.worker_id, timeout=5)
            
            if not task_id:
                continue
            
            print(f"[Worker {self.worker_id}] Received task: {task_id}")
            
            # Update worker status
            self.redis_client.set_worker_status(self.worker_id, "busy")
            
            # Get task details
            task_meta = self.redis_client.get_task_metadata(task_id)
            request_dict = task_meta.get("request")
            
            # Convert to RolloutRequest
            request = RolloutRequest(**request_dict)
            
            # Execute rollout
            result = await self.executor.execute(request)
            result.worker_id = self.worker_id
            
            # Store result
            self.redis_client.store_result(task_id, result.dict(), ttl=3600)
            
            # Update task status
            self.redis_client.set_task_metadata(task_id, {
                "status": result.status,
                "completed_at": result.completed_at,
            })
            
            # Update worker status
            self.redis_client.set_worker_status(self.worker_id, "idle")
            
            # Increment tasks completed
            worker_status = self.redis_client.get_worker_status(self.worker_id)
            if result.status == "completed":
                completed = worker_status.get("tasks_completed", 0) + 1
                failed = worker_status.get("tasks_failed", 0)
            else:
                completed = worker_status.get("tasks_completed", 0)
                failed = worker_status.get("tasks_failed", 0) + 1
            
            self.redis_client.set_worker_metadata(self.worker_id, {
                "tasks_completed": completed,
                "tasks_failed": failed,
                "current_task": None,
            })
            
            print(f"[Worker {self.worker_id}] Task {task_id} completed with status: {result.status}")
    
    def shutdown(self):
        """Shutdown worker."""
        self.running = False
        # Mark as dead in Redis
        self.redis_client.set_worker_status(self.worker_id, "dead")
        print(f"[Worker {self.worker_id}] Shutting down")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Worker Unit")
    parser.add_argument("--worker-id", required=True, help="Worker ID")
    args = parser.parse_args()
    
    # Load config
    config = Config("config.yaml")
    
    # Initialize Redis client
    redis_config = config.redis
    redis_client = RedisClient(
        host=redis_config.get("host", "localhost"),
        port=redis_config.get("port", 6379),
        db=redis_config.get("db", 0),
        password=redis_config.get("password"),
    )
    
    # Create worker
    worker = WorkerUnit(args.worker_id, redis_client)
    
    # Run worker
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
