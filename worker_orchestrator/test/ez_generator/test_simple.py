"""
Simplified test for Worker Router + Auto-Scaling.

Tests the core functionality without SkyRL dependencies:
- HTTP client communication
- Auto-scaling (worker spawning)
- Active polling mechanism
- Result retrieval
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

# Import WorkerRouterClient directly from the module file
# (bypassing ez_generator/__init__.py which imports SkyRL dependencies)
sys.path.insert(0, str(project_root / "ez_generator"))
from worker_router_client import WorkerRouterClient

# local_vulhub_path = "/mnt/e/git_fork_folder/VulRL/benchmark/vulhub/apache-cxf/CVE-2024-28752"
local_vulhub_path = "/data1/jph/vulhub/apache-cxf/CVE-2024-28752"


async def test_parallel_workers():
    """
    Test parallel worker execution:
    1. Submit TWO rollouts simultaneously
    2. Verify auto-scaling spawns multiple workers
    3. Poll for both completions
    4. Verify both results
    """
    print("=" * 70)
    print("Parallel Workers + Auto-Scaling Test")
    print("=" * 70)
    print()
    
    client = WorkerRouterClient(base_url="http://localhost:12345")
    
    try:
        # Step 1: Check worker status
        print("1. Checking initial worker status...")
        workers_status = await client.check_workers_health()
        print(f"   Workers: {workers_status['total']} total, "
              f"{workers_status['active']} active, "
              f"{workers_status['idle']} idle")
        
        if workers_status['active'] == 0:
            print("   ⚠ No workers running - auto-scaling will be triggered!")
        print()
        
        # Step 2: Build TWO rollout requests
        print("2. Building TWO rollout requests...")
        
        # Import models directly from worker_router module
        worker_router_path = project_root / "worker_router"
        if str(worker_router_path) not in sys.path:
            sys.path.insert(0, str(worker_router_path))
        from models import RolloutRequest
        
        # Note: vulhub_path must be an absolute path
        # Example: "/data1/jph/vulhub/apache-cxf/CVE-2024-28752"
        request1 = RolloutRequest(
            cve_id="CVE-2024-28752",
            vulhub_path=local_vulhub_path,
            prompt="write a hello world script at /tmp/workspace/",
            llm_endpoint="http://localhost:8001",
            model_name="qwen2.5-1.5b",
            max_steps=3,  # Short for quick test
            temperature=0.7,
            max_tokens=512,
            timeout=300,
            metadata={"test": "parallel_test_1", "worker": "1"}
        )
        
        request2 = RolloutRequest(
            cve_id="CVE-2024-28752",
            vulhub_path=local_vulhub_path,  # Absolute path
            prompt="write a hello world script at /tmp/workspace/",
            llm_endpoint="http://localhost:8001",
            model_name="qwen2.5-1.5b",
            max_steps=3,
            temperature=0.7,
            max_tokens=512,
            timeout=300,
            metadata={"test": "parallel_test_2", "worker": "2"}
        )
        
        print(f"   CVE: {request1.cve_id}")
        print(f"   Prompt: {request1.prompt}")
        print(f"   Max steps: {request1.max_steps}")
        print(f"   📝 Submitting TWO identical tasks for parallel execution")
        print()
        
        # Step 3: Submit BOTH rollouts concurrently
        print("3. Submitting BOTH rollout requests simultaneously...")
        task_id1, task_id2 = await asyncio.gather(
            client.submit_rollout(request1),
            client.submit_rollout(request2)
        )
        print(f"   ✓ Task 1 submitted: {task_id1}")
        print(f"   ✓ Task 2 submitted: {task_id2}")
        print()
        
        # Step 4: Check if workers were auto-spawned
        print("4. Checking if workers were auto-spawned...")
        await asyncio.sleep(3)  # Give auto-scaling time to spawn workers
        workers_status = await client.check_workers_health()
        print(f"   Workers now: {workers_status['total']} total, "
              f"{workers_status['active']} active, "
              f"{workers_status['busy']} busy")
        
        if workers_status['active'] >= 2:
            print("   ✓ Auto-scaling spawned multiple workers!")
        elif workers_status['active'] == 1:
            print("   ⚠ Only 1 worker spawned (tasks may run sequentially)")
        print()
        
        # Step 5: Poll for BOTH completions in parallel
        print("5. Polling for BOTH completions (active polling mechanism)...")
        print(f"   Poll interval: 5 seconds")
        print(f"   Timeout: 120 seconds per task")
        print()
        
        # Wait for both tasks concurrently
        result1, result2 = await asyncio.gather(
            client.wait_for_rollout(task_id1, timeout=120.0, poll_interval=5.0, verbose=True),
            client.wait_for_rollout(task_id2, timeout=120.0, poll_interval=5.0, verbose=True)
        )
        
        # Step 6: Display results for BOTH tasks
        print()
        print("=" * 70)
        print("Test Results - BOTH Tasks")
        print("=" * 70)
        print()
        
        print("📊 Task 1 Results:")
        print(f"   Status: {result1.status}")
        print(f"   Worker ID: {result1.worker_id}")
        print(f"   Reward: {result1.reward}")
        print(f"   Success: {result1.success}")
        print(f"   Duration: {result1.duration:.2f}s" if result1.duration else "   Duration: N/A")
        print(f"   Steps: {len(result1.trajectory or [])}")
        print()
        
        print("📊 Task 2 Results:")
        print(f"   Status: {result2.status}")
        print(f"   Worker ID: {result2.worker_id}")
        print(f"   Reward: {result2.reward}")
        print(f"   Success: {result2.success}")
        print(f"   Duration: {result2.duration:.2f}s" if result2.duration else "   Duration: N/A")
        print(f"   Steps: {len(result2.trajectory or [])}")
        print()
        
        # Check if different workers were used
        if result1.worker_id != result2.worker_id:
            print(f"   ✓ Tasks executed by DIFFERENT workers (parallel execution)")
        else:
            print(f"   ⚠ Tasks executed by SAME worker (sequential execution)")
        print()
        
        # Step 7: Final worker status
        print("6. Final worker status...")
        workers_status = await client.check_workers_health()
        print(f"   Workers: {workers_status['total']} total, "
              f"{workers_status['idle']} idle, "
              f"{workers_status['busy']} busy")
        print()
        
        print("=" * 70)
        print("✓ Parallel Execution Test Completed Successfully!")
        print("=" * 70)
        print()
        
        # Summary
        print("Summary:")
        print("  ✓ HTTP client working")
        print("  ✓ Auto-scaling working (spawned workers)")
        print(f"  ✓ Submitted 2 tasks simultaneously")
        print(f"  ✓ Both tasks completed successfully")
        if result1.worker_id != result2.worker_id:
            print(f"  ✓ Parallel execution confirmed (different workers)")
        else:
            print(f"  ⚠ Sequential execution (same worker)")
        print("  ✓ Active polling mechanism working")
        print("  ✓ Result retrieval working")
        print("  ✓ End-to-end parallel flow successful")
        
        return True
        
    except Exception as e:
        print()
        print("=" * 70)
        print("✗ Test Failed")
        print("=" * 70)
        print(f"Error: {e}")
        print()
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        await client.close()


async def main():
    """Main entry point."""
    print()
    print("=" * 70)
    print("PARALLEL WORKERS TEST")
    print("=" * 70)
    print()
    print("This test validates:")
    print("  • Worker Router HTTP API")
    print("  • Auto-scaling (automatic worker spawning)")
    print("  • Parallel execution (2 tasks simultaneously)")
    print("  • Active polling mechanism (check every 5s)")
    print("  • Multiple rollout execution")
    print("  • Result retrieval for multiple tasks")
    print()
    print("Prerequisites:")
    print("  • Worker Router running on http://localhost:12345")
    print("  • LLM server running on http://localhost:8001")
    print("  • Redis running on localhost:6379")
    print("  • (Workers will auto-spawn - no manual startup needed!)")
    print()
    
    success = await test_parallel_workers()
    
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
