"""HTTP client for Worker Router API with active polling."""

import aiohttp
import asyncio
import time
from typing import Optional, Dict, Any
import sys
from pathlib import Path

# Add worker_router to path for model imports
_worker_router_path = Path(__file__).parent.parent / "worker_router"
if str(_worker_router_path) not in sys.path:
    sys.path.insert(0, str(_worker_router_path))

# Import directly from models module to avoid package __init__.py
from models import (
    RolloutRequest,
    RolloutResponse,
    RolloutResult,
    WorkersStatusResponse,
)


class WorkerRouterClient:
    """
    HTTP client for Worker Router API with active polling.
    
    The client submits rollout requests and actively polls for results,
    since worker units push results to Redis asynchronously.
    """
    
    def __init__(self, base_url: str = "http://localhost:12345"):
        """
        Initialize the client.
        
        Args:
            base_url: Base URL of the Worker Router API (default: http://localhost:12345)
        """
        self.base_url = base_url.rstrip("/")
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _ensure_session(self):
        """Lazy session initialization."""
        if self.session is None:
            self.session = aiohttp.ClientSession()
    
    async def close(self):
        """Close the HTTP session."""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def submit_rollout(self, request: RolloutRequest) -> str:
        """
        Submit a rollout request to worker router.
        
        POST /api/rollout/execute
        
        Args:
            request: Rollout request with CVE info, prompt, LLM config, etc.
            
        Returns:
            task_id: Unique task identifier for polling
        """
        await self._ensure_session()
        
        url = f"{self.base_url}/api/rollout/execute"
        
        try:
            async with self.session.post(url, json=request.dict()) as resp:
                resp.raise_for_status()
                data = await resp.json()
                response = RolloutResponse(**data)
                return response.task_id
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Failed to submit rollout: {e}")
    
    async def get_rollout_status(self, task_id: str) -> RolloutResult:
        """
        Get current status of a rollout task.
        
        GET /api/rollout/status/{task_id}
        
        Args:
            task_id: Task identifier from submit_rollout()
            
        Returns:
            RolloutResult with current status and result (if completed)
        """
        await self._ensure_session()
        
        url = f"{self.base_url}/api/rollout/status/{task_id}"
        
        try:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return RolloutResult(**data)
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Failed to get rollout status: {e}")
    
    async def wait_for_rollout(
        self,
        task_id: str,
        timeout: float = 600.0,
        poll_interval: float = 10.0,
        verbose: bool = True,
    ) -> RolloutResult:
        """
        ACTIVE POLLING LOOP: Wait for rollout to complete.
        
        This method polls GET /api/rollout/status/{task_id} every poll_interval
        seconds until the rollout completes or fails.
        
        Args:
            task_id: Task identifier from submit_rollout()
            timeout: Maximum time to wait in seconds (default: 600s = 10 minutes)
            poll_interval: Time between status checks in seconds (default: 10s)
            verbose: Print polling progress
            
        Returns:
            RolloutResult with trajectory and reward
            
        Raises:
            TimeoutError: If rollout doesn't complete within timeout
            RuntimeError: If rollout fails
        """
        start_time = time.time()
        poll_count = 0
        
        if verbose:
            print(f"[WorkerRouterClient] Waiting for task {task_id}")
            print(f"[WorkerRouterClient] Timeout: {timeout}s, Poll interval: {poll_interval}s")
        
        # Add retry logic for network errors during polling
        max_retries = 3
        retry_count = 0
        
        while True:
            elapsed = time.time() - start_time
            
            # Check timeout
            if elapsed > timeout:
                raise TimeoutError(
                    f"Rollout {task_id} did not complete within {timeout}s "
                    f"(polled {poll_count} times)"
                )
            
            try:
                # Poll status
                poll_count += 1
                result = await self.get_rollout_status(task_id)
                retry_count = 0  # Reset retry count on success
                
                if verbose:
                    print(
                        f"[WorkerRouterClient] Poll #{poll_count} ({elapsed:.1f}s): "
                        f"status={result.status}"
                    )
                
                # Check if completed
                if result.status == "completed":
                    if verbose:
                        print(f"[WorkerRouterClient] ✓ Task completed after {elapsed:.1f}s")
                        print(f"[WorkerRouterClient] Reward: {result.reward}, Steps: {len(result.trajectory or [])}")
                    return result
                
                # Check if failed
                if result.status == "failed":
                    error_msg = result.error or "Unknown error"
                    raise RuntimeError(
                        f"Rollout {task_id} failed: {error_msg}"
                    )
                
                # Check if timeout
                if result.status == "timeout":
                    raise TimeoutError(
                        f"Rollout {task_id} timed out on worker side"
                    )
                
                # Status is 'queued' or 'running' - keep waiting
                await asyncio.sleep(poll_interval)
                
            except (aiohttp.ClientError, RuntimeError) as e:
                # Network error during polling - retry with backoff
                retry_count += 1
                if retry_count > max_retries:
                    raise RuntimeError(
                        f"Failed to poll status after {max_retries} retries: {e}"
                    )
                
                backoff = poll_interval * (2 ** (retry_count - 1))
                if verbose:
                    print(
                        f"[WorkerRouterClient] ⚠ Poll error, "
                        f"retry {retry_count}/{max_retries} in {backoff:.1f}s: {e}"
                    )
                await asyncio.sleep(backoff)
    
    async def check_workers_health(self) -> Dict[str, Any]:
        """
        Check if workers are available and healthy.
        
        GET /api/workers/status
        
        Returns:
            WorkersStatusResponse with worker stats
        """
        await self._ensure_session()
        
        url = f"{self.base_url}/api/workers/status"
        
        try:
            async with self.session.get(url) as resp:
                resp.raise_for_status()
                data = await resp.json()
                return data
        except aiohttp.ClientError as e:
            raise RuntimeError(f"Failed to check workers health: {e}")
    
    async def check_health(self) -> bool:
        """
        Check if Worker Router API is healthy.
        
        GET /health
        
        Returns:
            True if healthy, False otherwise
        """
        await self._ensure_session()
        
        url = f"{self.base_url}/health"
        
        try:
            async with self.session.get(url) as resp:
                return resp.status == 200
        except aiohttp.ClientError:
            return False
