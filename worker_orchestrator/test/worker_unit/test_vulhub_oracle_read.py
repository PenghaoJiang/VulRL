"""
Test Vulhub Read-based Oracle Mode (SQLi, LFI)

This test validates the read-based oracle functionality where:
1. A random flag is generated before agent execution
2. oracle_flag_setup.sh inserts the flag into the target
3. Agent (or oracle_solution.sh) tries to extract the flag
4. reward_type="vulhub_read" checks if flag appears in trajectory observations
5. Reward should be 1.0 if flag is found in observations

Test cases:
- django/CVE-2021-35042 (SQLi)
- django/CVE-2022-34265 (SQLi)
- flink/CVE-2020-17519 (LFI)
- coldfusion/CVE-2010-2861 (LFI)
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


async def test_vulhub_read_oracle(
    vulhub_path: str,
    cve_id: str,
    vuln_type: str = "SQLi/LFI"
):
    """Test Vulhub read-based oracle mode."""
    
    print("=" * 70)
    print(f"Vulhub Read Oracle Test - {vuln_type} ({vulhub_path})")
    print("=" * 70)
    print()
    
    vulhub_base_path = str(_DEFAULT_VULHUB_BENCHMARK_ROOT.resolve())
    
    # Verify oracle files exist
    case_dir = Path(vulhub_base_path) / vulhub_path
    oracle_flag_setup = case_dir / "oracle_flag_setup.sh"
    oracle_solution = case_dir / "oracle_solution.sh"
    oracle_test = case_dir / "oracle_test.sh"
    
    print(f"Checking oracle files in: {case_dir}")
    if not oracle_flag_setup.exists():
        print(f"✗ Error: oracle_flag_setup.sh not found at {oracle_flag_setup}")
        return 1
    if not oracle_solution.exists():
        print(f"✗ Error: oracle_solution.sh not found at {oracle_solution}")
        return 1
    if not oracle_test.exists():
        print(f"✗ Error: oracle_test.sh not found at {oracle_test}")
        return 1
    print(f"✓ All oracle files found")
    print()
    
    # Create test request with oracle mode + read reward
    request = RolloutRequest(
        cve_id=cve_id,
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
            "is_oracle": True,  # Enable oracle mode (uses oracle_solution.sh)
            "reward_type": "vulhub_read",  # Use read-based reward (flag extraction)
        }
    )
    
    print("Test Configuration:")
    print(f"  Mode: ORACLE (oracle_solution.sh execution)")
    print(f"  Reward Type: vulhub_read (flag extraction verification)")
    print(f"  Vulnerability Type: {vuln_type}")
    print(f"  CVE ID: {request.cve_id}")
    print(f"  Vulhub Path: {request.vulhub_path}")
    print(f"  Vulhub Base: {vulhub_base_path}")
    print(f"  is_oracle: True")
    print()
    print("Expected Flow:")
    print("  1. Generate random flag (flag_[a-z0-9]{{20}})")
    print("  2. Run oracle_flag_setup.sh (insert flag into target)")
    print("  3. Run oracle_solution.sh (extract flag)")
    print("  4. Check if flag appears in observations")
    print("  5. Reward = 1.0 if flag found, 0.0 otherwise")
    print()
    
    # Execute rollout with oracle mode + read reward
    executor = RolloutExecutor()
    
    try:
        print("Executing read-based oracle rollout...")
        print()
        result = await executor.execute(request, agent_type="ctf")
        
        print("=" * 70)
        print("Read-based Oracle Rollout Result")
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
                print(f"✓ PERFECT! Reward={result.reward} (flag successfully extracted)")
                print(f"  The oracle solution extracted the flag from the vulnerability")
                print(f"  and it appeared in the trajectory observations.")
            elif result.reward > 0.0:
                print(f"⚠ UNEXPECTED! Reward={result.reward} (expected 0.0 or 1.0)")
            else:
                print(f"✗ FAILED! Reward={result.reward} (flag not extracted)")
                print(f"  The oracle solution may not have executed correctly,")
                print(f"  or the flag was not found in observations.")
            print()
        
        if result.trajectory:
            print("Trajectory Summary:")
            for step in result.trajectory:
                print(f"\n  Step {step.step}:")
                action_str = str(step.action)[:150]
                print(f"    🎯 Action: {action_str}{'...' if len(str(step.action)) > 150 else ''}")
                obs_str = str(step.observation)[:200]
                print(f"    📝 Observation: {obs_str}{'...' if len(str(step.observation)) > 200 else ''}")
                print(f"    Done: {step.done}")
        
        # Print result summary
        print("\n" + "=" * 70)
        print("Test Result Summary")
        print("=" * 70)
        print(f"CVE: {cve_id}")
        print(f"Path: {vulhub_path}")
        print(f"Type: {vuln_type}")
        print(f"Reward: {result.reward}")
        print(f"Status: {result.status}")
        print()
        
        if result.error:
            print(f"\n✗ Error: {result.error}")
            return 1
        else:
            if result.reward == 1.0:
                print(f"✓ Read-based oracle test passed: reward=1.0 (flag extracted)")
                return 0
            else:
                print(f"⚠ Read-based oracle test failed: reward={result.reward} (expected 1.0)")
                return 1
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


async def test_all_read_cases():
    """Test all read-based oracle cases."""
    print("\n" + "=" * 70)
    print("Testing All Read-based Oracle Cases")
    print("=" * 70)
    print()
    
    test_cases = [
        # SQLi cases
        ("django/CVE-2021-35042", "CVE-2021-35042", "SQLi (MySQL error-based)"),
        ("django/CVE-2022-34265", "CVE-2022-34265", "SQLi (PostgreSQL error-based)"),
        # LFI cases
        ("flink/CVE-2020-17519", "CVE-2020-17519", "LFI (Path Traversal)"),
        ("coldfusion/CVE-2010-2861", "CVE-2010-2861", "LFI (Directory Traversal)"),
    ]
    
    results = []
    
    for vulhub_path, cve_id, vuln_type in test_cases:
        print(f"\n{'='*70}")
        print(f"Testing: {vulhub_path}")
        print(f"{'='*70}\n")
        
        exit_code = await test_vulhub_read_oracle(vulhub_path, cve_id, vuln_type)
        results.append((vulhub_path, vuln_type, exit_code))
        
        print("\n" + "-" * 70 + "\n")
    
    # Print summary
    print("\n" + "=" * 70)
    print("Overall Test Summary")
    print("=" * 70)
    for path, vuln_type, code in results:
        status = "✓ PASS" if code == 0 else "✗ FAIL"
        print(f"{status} | {path} ({vuln_type})")
    print()
    
    # Return 0 if all passed, 1 if any failed
    return 0 if all(code == 0 for _, _, code in results) else 1


if __name__ == "__main__":
    print("\nRunning Vulhub Read-based Oracle Tests\n")
    
    # Test option: single case or all cases
    import sys
    if len(sys.argv) > 1:
        # Test specific case
        if sys.argv[1] == "django-sqli":
            exit_code = asyncio.run(test_vulhub_read_oracle(
                "django/CVE-2021-35042", 
                "CVE-2021-35042", 
                "SQLi (MySQL)"
            ))
        elif sys.argv[1] == "flink-lfi":
            exit_code = asyncio.run(test_vulhub_read_oracle(
                "flink/CVE-2020-17519", 
                "CVE-2020-17519", 
                "LFI"
            ))
        elif sys.argv[1] == "coldfusion-lfi":
            exit_code = asyncio.run(test_vulhub_read_oracle(
                "coldfusion/CVE-2010-2861", 
                "CVE-2010-2861", 
                "LFI"
            ))
        else:
            print(f"Unknown test case: {sys.argv[1]}")
            print("Available: django-sqli, flink-lfi, coldfusion-lfi, or run without args for all")
            exit_code = 1
    else:
        # Test single case by default (fastest for quick validation)
        print("Testing single case: django/CVE-2021-35042 (SQLi)")
        print("Run with 'all' argument to test all cases")
        print()
        exit_code = asyncio.run(test_vulhub_read_oracle(
            "django/CVE-2021-35042", 
            "CVE-2021-35042", 
            "SQLi (MySQL)"
        ))
    
    sys.exit(exit_code)
