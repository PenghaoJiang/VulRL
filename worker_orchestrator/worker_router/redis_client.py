"""Redis client wrapper for Worker Router."""

import redis
import json
import time
from typing import Optional, Dict, Any, List


class RedisClient:
    """Redis operations wrapper."""
    
    def __init__(self, host: str, port: int, db: int = 0, password: Optional[str] = None):
        """Initialize Redis client.
        
        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password (optional)
        """
        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            password=password if password else None,
            decode_responses=True
        )
    
    # ============================================
    # Task Queue Operations
    # ============================================
    
    def push_task(self, worker_id: str, task_id: str):
        """Push task to worker queue.
        
        Args:
            worker_id: Worker ID
            task_id: Task ID
        """
        queue_key = f"worker:{worker_id}:queue"
        self.client.lpush(queue_key, task_id)
    
    def pop_task(self, worker_id: str, timeout: int = 5) -> Optional[str]:
        """Pop task from worker queue (blocking).
        
        Args:
            worker_id: Worker ID
            timeout: Timeout in seconds
            
        Returns:
            Task ID or None if timeout
        """
        queue_key = f"worker:{worker_id}:queue"
        result = self.client.brpop(queue_key, timeout=timeout)
        if result:
            return result[1]  # (queue_key, task_id)
        return None
    
    def get_queue_length(self, worker_id: str) -> int:
        """Get queue length for worker.
        
        Args:
            worker_id: Worker ID
            
        Returns:
            Queue length
        """
        queue_key = f"worker:{worker_id}:queue"
        return self.client.llen(queue_key)
    
    # ============================================
    # Worker State Operations
    # ============================================
    
    def set_worker_status(self, worker_id: str, status: str):
        """Set worker status.
        
        Args:
            worker_id: Worker ID
            status: Status (idle/busy/dead)
        """
        key = f"worker:{worker_id}"
        self.client.hset(key, "status", status)
    
    def get_worker_status(self, worker_id: str) -> Dict[str, Any]:
        """Get worker status.
        
        Args:
            worker_id: Worker ID
            
        Returns:
            Worker status dict
        """
        key = f"worker:{worker_id}"
        data = self.client.hgetall(key)
        if not data:
            return {}
        
        # Convert string values to appropriate types
        return {
            "worker_id": worker_id,
            "status": data.get("status", "dead"),
            "pid": int(data.get("pid", 0)),
            "started_at": float(data.get("started_at", 0)),
            "current_task": data.get("current_task") if data.get("current_task") != "None" else None,
            "tasks_completed": int(data.get("tasks_completed", 0)),
            "tasks_failed": int(data.get("tasks_failed", 0)),
        }
    
    def set_worker_metadata(self, worker_id: str, data: Dict[str, Any]):
        """Set worker metadata.
        
        Args:
            worker_id: Worker ID
            data: Metadata dict
        """
        key = f"worker:{worker_id}"
        # Convert None to string for Redis
        redis_data = {}
        for k, v in data.items():
            redis_data[k] = str(v) if v is not None else "None"
        self.client.hset(key, mapping=redis_data)
    
    def get_all_workers(self) -> List[str]:
        """Get all worker IDs.
        
        Returns:
            List of worker IDs
        """
        keys = self.client.keys("worker:*")
        worker_ids = []
        for key in keys:
            if ":queue" not in key:
                worker_id = key.replace("worker:", "")
                worker_ids.append(worker_id)
        return worker_ids
    
    def delete_worker(self, worker_id: str):
        """Delete worker from Redis.
        
        Args:
            worker_id: Worker ID
        """
        self.client.delete(f"worker:{worker_id}")
        self.client.delete(f"worker:{worker_id}:queue")
    
    # ============================================
    # Task Metadata Operations
    # ============================================
    
    def set_task_metadata(self, task_id: str, data: Dict[str, Any]):
        """Set task metadata.
        
        Args:
            task_id: Task ID
            data: Metadata dict
        """
        key = f"task:{task_id}"
        redis_data = {}
        for k, v in data.items():
            if isinstance(v, (dict, list)):
                redis_data[k] = json.dumps(v)
            else:
                redis_data[k] = str(v) if v is not None else "None"
        self.client.hset(key, mapping=redis_data)
    
    def get_task_metadata(self, task_id: str) -> Dict[str, Any]:
        """Get task metadata.
        
        Args:
            task_id: Task ID
            
        Returns:
            Task metadata dict
        """
        key = f"task:{task_id}"
        data = self.client.hgetall(key)
        if not data:
            return {}
        
        # Parse JSON strings
        result = {}
        for k, v in data.items():
            if k == "request":
                result[k] = json.loads(v)
            elif v == "None":
                result[k] = None
            else:
                result[k] = v
        return result
    
    def set_task_status(self, task_id: str, status: str):
        """Set task status.
        
        Args:
            task_id: Task ID
            status: Status (queued/running/completed/failed/timeout)
        """
        key = f"task:{task_id}"
        self.client.hset(key, "status", status)
    
    # ============================================
    # Result Storage Operations
    # ============================================
    
    def store_result(self, task_id: str, result: Dict[str, Any], ttl: int = 3600):
        """Store task result with TTL.
        
        Args:
            task_id: Task ID
            result: Result dict
            ttl: Time to live in seconds
        """
        key = f"result:{task_id}"
        self.client.set(key, json.dumps(result), ex=ttl)
    
    def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get task result.
        
        Args:
            task_id: Task ID
            
        Returns:
            Result dict or None
        """
        key = f"result:{task_id}"
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None
    
    # ============================================
    # Utility Operations
    # ============================================
    
    def ping(self) -> bool:
        """Check Redis connection.
        
        Returns:
            True if connected
        """
        return self.client.ping()
