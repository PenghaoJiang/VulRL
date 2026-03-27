"""
Standalone test for Worker Unit Rollout Executor

Test case:
- CVE: apache-cxf/CVE-2024-28752
- Path: /mnt/e/git_fork_folder/VulRL/benchmark/vulhub/apache-cxf/CVE-2024-28752
- Prompt: "write a hello world script at /tmp/workspace/"
- LLM: http://127.0.0.1:8001

Note: Uses VulhubAdapterTest (subprocess-based) to avoid Docker SDK proxy issues.
"""

import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Monkey-patch to use subprocess-based adapter BEFORE other imports
# This avoids Docker SDK proxy issues in WSL2 (因为老子用cursor要开梯子，wsl自动继承proxy 来下各种依赖)

print("[TEST] Patching to use VulhubAdapterTest (subprocess-based)")
import worker_unit.docker as docker_module
from worker_unit.docker.vulhub_adapter_test import VulhubAdapterTest
docker_module.VulhubAdapter = VulhubAdapterTest

# Now import the rest
from worker_unit.rollout_executor import RolloutExecutor
from worker_router.models import RolloutRequest


async def test_rollout():
    """Test rollout executor with CVE-2024-28752."""
    
    print("=" * 70)
    print("Worker Unit Rollout Test")
    print("=" * 70)
    print()
    
    # Create test request
    request = RolloutRequest(
        cve_id="CVE-2024-28752",
        vulhub_path="/mnt/e/git_fork_folder/VulRL/benchmark/vulhub/apache-cxf/CVE-2024-28752",  # Absolute path
        prompt="write a hello world script at /tmp/workspace/",
        max_steps=5,
        timeout=300,
        llm_endpoint="http://127.0.0.1:8001",
        model_name="qwen2.5-1.5b",
        temperature=0.7,
        max_tokens=512,
        metadata={}
    )
    
    print("Test Configuration:")
    print(f"  CVE ID: {request.cve_id}")
    print(f"  Vulhub Path: {request.vulhub_path}")
    print(f"  Prompt: {request.prompt}")
    print(f"  Max Steps: {request.max_steps}")
    print(f"  LLM: {request.llm_endpoint}")
    print()
    
    # Execute rollout
    executor = RolloutExecutor()
    
    try:
        print("Executing rollout...")
        print()
        result = await executor.execute(request)
        
        print("=" * 70)
        print("Rollout Result")
        print("=" * 70)
        print(f"Status: {result.status}")
        print(f"Reward: {result.reward}")
        print(f"Success: {result.success}")
        print(f"Duration: {result.duration:.2f}s")
        print(f"Steps: {len(result.trajectory) if result.trajectory else 0}")
        print()
        
        if result.trajectory:
            print("Trajectory:")
            for step in result.trajectory:
                print(f"\n  Step {step.step}:")
                print(f"    Action: {step.action[:100]}...")
                print(f"    Observation: {step.observation[:100]}...")
                print(f"    Reward: {step.reward}")
                print(f"    Done: {step.done}")
        
        if result.error:
            print(f"\n✗ Error: {result.error}")
            return 1
        else:
            print("\n✓ Rollout completed successfully!")
            return 0
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_rollout())
    sys.exit(exit_code)
