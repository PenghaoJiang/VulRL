"""
Test Vulhub Oracle Mode with RCE Reward

This test validates the oracle mode functionality where:
1. is_oracle=True triggers oracle_solution.sh execution instead of LLM agent
2. reward_type="vulhub_rce" uses oracle_test.sh to verify exploit success
3. Reward should be 1.0 if oracle_test.sh exits with code 0

Test case: aj-report/CNVD-2024-15077
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from worker_unit.rollout_executor import RolloutExecutor
from worker_router.models import RolloutRequest

# Compute repo root and benchmark paths (portable across machines)
_REPO_ROOT = Path(__file__).resolve().parents[3]  # test/worker_unit -> worker_orchestrator -> VulRL
_DEFAULT_VULHUB_BENCHMARK_ROOT = _REPO_ROOT / "benchmark" / "vulhub"


async def test_vulhub_oracle():
    """Test Vulhub oracle mode with RCE reward."""
    
    print("=" * 70)
    print("Vulhub Oracle Test - RCE Reward (aj-report/CNVD-2024-15077)")
    print("=" * 70)
    print()
    
    vulhub_path = "aj-report/CNVD-2024-15077"
    vulhub_base_path = str(_DEFAULT_VULHUB_BENCHMARK_ROOT.resolve())
    
    # Verify oracle files exist
    case_dir = Path(vulhub_base_path) / vulhub_path
    oracle_solution = case_dir / "oracle_solution.sh"
    oracle_test = case_dir / "oracle_test.sh"
    
    print(f"Checking oracle files in: {case_dir}")
    if not oracle_solution.exists():
        print(f"✗ Error: oracle_solution.sh not found at {oracle_solution}")
        return 1
    if not oracle_test.exists():
        print(f"✗ Error: oracle_test.sh not found at {oracle_test}")
        return 1
    print(f"✓ Oracle files found")
    print()
    
    # Create test request with oracle mode enabled
    request = RolloutRequest(
        cve_id="CNVD-2024-15077",
        vulhub_path=vulhub_path,
        prompt="[Oracle mode - no prompt needed]",
        max_steps=1,  # Not used in oracle mode
        timeout=300,
        llm_endpoint="http://127.0.0.1:30000",  # Not used in oracle mode
        model_name="qwen3.5-9b",  # Not used in oracle mode
        temperature=0.7,
        max_tokens=1024,
        metadata={
            "agent_type": "ctf",
            "vulhub_base_path": vulhub_base_path,
            "is_oracle": True,  # Enable oracle mode
            "reward_type": "vulhub_rce",  # Use RCE reward (oracle_test.sh)
        }
    )
    
    print("Test Configuration:")
    print(f"  Mode: ORACLE (oracle_solution.sh execution)")
    print(f"  Reward Type: vulhub_rce (oracle_test.sh verification)")
    print(f"  CVE ID: {request.cve_id}")
    print(f"  Vulhub Path: {request.vulhub_path}")
    print(f"  Vulhub Base: {vulhub_base_path}")
    print(f"  is_oracle: True")
    print()
    
    # Execute rollout with oracle mode
    executor = RolloutExecutor()
    
    try:
        print("Executing oracle rollout...")
        print()
        result = await executor.execute(request, agent_type="ctf")
        
        print("=" * 70)
        print("Oracle Rollout Result")
        print("=" * 70)
        print(f"Status: {result.status}")
        print(f"Reward: {result.reward}")
        print(f"Success: {result.success}")
        print(f"Duration: {result.duration:.2f}s")
        print(f"Steps: {len(result.trajectory) if result.trajectory else 0}")
        print()
        
        # Analyze reward
        if result.reward is not None:
            print("=" * 70)
            print("Reward Analysis")
            print("=" * 70)
            if result.reward == 1.0:
                print(f"✓ PERFECT! Reward={result.reward} (oracle_test.sh PASSED)")
                print(f"  The oracle solution successfully exploited the vulnerability")
                print(f"  and the oracle test verified the exploit artifact.")
            elif result.reward > 0.0:
                print(f"⚠ UNEXPECTED! Reward={result.reward} (expected 0.0 or 1.0)")
            else:
                print(f"✗ FAILED! Reward={result.reward} (oracle_test.sh FAILED)")
                print(f"  The oracle solution may not have executed correctly,")
                print(f"  or the test could not find the expected artifact.")
            print()
        
        if result.trajectory:
            print("Trajectory Summary:")
            for step in result.trajectory:
                print(f"\n  Step {step.step}:")
                action_str = str(step.action)[:150]
                print(f"    🎯 Action: {action_str}{'...' if len(str(step.action)) > 150 else ''}")
                obs_str = str(step.observation)[:150]
                print(f"    📝 Observation: {obs_str}{'...' if len(str(step.observation)) > 150 else ''}")
                print(f"    Done: {step.done}")
                if hasattr(step, 'metadata') and step.metadata:
                    print(f"    Metadata: {step.metadata}")
        
        # Print full result
        print("\n" + "=" * 70)
        print("Full Rollout Result (dict format)")
        print("=" * 70)
        result_dict = result.model_dump()
        # Truncate long fields for readability
        if result_dict.get('trajectory'):
            for step in result_dict['trajectory']:
                for key in ['action', 'observation', 'thought', 'response']:
                    if key in step.get('metadata', {}) and len(str(step['metadata'][key])) > 200:
                        step['metadata'][key] = str(step['metadata'][key])[:200] + '...'
                if 'observation' in step and len(str(step['observation'])) > 200:
                    step['observation'] = str(step['observation'])[:200] + '...'
                if 'action' in step and len(str(step['action'])) > 200:
                    step['action'] = str(step['action'])[:200] + '...'
        print(json.dumps(result_dict, indent=2, default=str))
        print()
        
        if result.error:
            print(f"\n✗ Error: {result.error}")
            return 1
        else:
            print("\n✓ Oracle test completed!")
            if result.reward == 1.0:
                print(f"✓ Oracle validation passed: reward=1.0 (exploit succeeded)")
                return 0
            else:
                print(f"⚠ Oracle validation failed: reward={result.reward} (expected 1.0)")
                return 1
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


async def test_vulhub_oracle_vs_normal():
    """
    Comparison test: Oracle mode vs Normal agent mode.
    
    This test runs the same case twice:
    1. With is_oracle=True (should get reward=1.0)
    2. With is_oracle=False (agent may or may not succeed)
    """
    print("\n" + "=" * 70)
    print("Comparison Test: Oracle vs Normal Agent")
    print("=" * 70)
    print()
    
    vulhub_path = "aj-report/CNVD-2024-15077"
    vulhub_base_path = str(_DEFAULT_VULHUB_BENCHMARK_ROOT.resolve())
    
    # Test 1: Oracle mode
    print("\n" + "-" * 70)
    print("Test 1: Oracle Mode (is_oracle=True)")
    print("-" * 70)
    
    request_oracle = RolloutRequest(
        cve_id="CNVD-2024-15077",
        vulhub_path=vulhub_path,
        prompt="[Oracle mode]",
        max_steps=1,
        timeout=300,
        llm_endpoint="http://127.0.0.1:30000",
        model_name="qwen3.5-9b",
        temperature=0.7,
        max_tokens=1024,
        metadata={
            "agent_type": "ctf",
            "vulhub_base_path": vulhub_base_path,
            "is_oracle": True,
            "reward_type": "vulhub_rce",
        }
    )
    
    executor = RolloutExecutor()
    result_oracle = await executor.execute(request_oracle, agent_type="ctf")
    
    print(f"\nOracle Result: reward={result_oracle.reward}, status={result_oracle.status}")
    
    # Test 2: Normal agent mode (optional - can be skipped if no LLM available)
    print("\n" + "-" * 70)
    print("Test 2: Normal Agent Mode (is_oracle=False)")
    print("-" * 70)
    print("Note: This test requires a running LLM server")
    print("Skipping for now (set is_oracle=False to enable)")
    print("-" * 70)
    
    # Uncomment to test with actual agent:
    # request_normal = RolloutRequest(
    #     cve_id="CNVD-2024-15077",
    #     vulhub_path=vulhub_path,
    #     prompt="Exploit the aj-report vulnerability",
    #     max_steps=15,
    #     timeout=300,
    #     llm_endpoint="http://127.0.0.1:30000",
    #     model_name="qwen3.5-9b",
    #     temperature=0.7,
    #     max_tokens=1024,
    #     metadata={
    #         "agent_type": "ctf",
    #         "vulhub_base_path": vulhub_base_path,
    #         "is_oracle": False,
    #         "reward_type": "vulhub_rce",
    #     }
    # )
    # result_normal = await executor.execute(request_normal, agent_type="ctf")
    # print(f"\nNormal Agent Result: reward={result_normal.reward}, status={result_normal.status}")
    
    # Summary
    print("\n" + "=" * 70)
    print("Comparison Summary")
    print("=" * 70)
    print(f"Oracle Mode:  reward={result_oracle.reward} (expected=1.0)")
    # print(f"Normal Agent: reward={result_normal.reward} (variable)")
    print()
    
    if result_oracle.reward == 1.0:
        print("✓ Oracle mode validation passed!")
        return 0
    else:
        print("✗ Oracle mode validation failed!")
        return 1


if __name__ == "__main__":
    print("\nRunning Vulhub Oracle Tests\n")
    
    # Test 1: Basic oracle mode test
    exit_code = asyncio.run(test_vulhub_oracle())
    
    # Test 2: Comparison test (optional)
    # exit_code = asyncio.run(test_vulhub_oracle_vs_normal())
    
    sys.exit(exit_code)
