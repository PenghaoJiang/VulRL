"""
Test CTF Agent (Advanced Agent)

Test case:
- Agent: CTF (advanced agent with thought/action parsing)
- CVE: apache-cxf/CVE-2024-28752
- Prompt: Penetration testing focused (using default_vul.yaml config)
- LLM: http://127.0.0.1:8001

Uses regular VulhubAdapter with Docker SDK and default_vul.yaml config for penetration testing.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from worker_unit.rollout_executor import RolloutExecutor
from worker_router.models import RolloutRequest


async def test_ctf_agent():
    """Test CTF agent with CVE-2024-28752."""
    
    print("=" * 70)
    print("CTF Agent Test")
    print("=" * 70)
    print()
    
    # Create test request for CTF agent
    request = RolloutRequest(
        cve_id="CVE-2024-28752-ctf",
        vulhub_path="apache-cxf/CVE-2024-28752",
        prompt="write a hello world script at /tmp/workspace/",
        # prompt="Identify and exploit vulnerabilities in the Apache CXF service. Document your findings.",
        max_steps=10,
        timeout=300,
        llm_endpoint="http://127.0.0.1:8001",
        model_name="qwen2.5-1.5b",
        temperature=0.7,
        max_tokens=1024,
        metadata={
            "agent_type": "ctf",
            # "vulhub_base_path": "/data1/jph/VulRL/benchmark/vulhub",
            "vulhub_base_path": "/mnt/e/git_fork_folder/VulRL/benchmark/vulhub",
            "agent_config_file": str(Path(__file__).parent.parent.parent / "worker_unit/agent/config/default_vul.yaml")
        }
    )
    
    print("Test Configuration:")
    print(f"  Agent Type: CTF (advanced)")
    print(f"  CVE ID: {request.cve_id}")
    print(f"  Vulhub Path: {request.vulhub_path}")
    print(f"  Prompt: {request.prompt}")
    print(f"  Max Steps: {request.max_steps}")
    print(f"  LLM: {request.llm_endpoint}")
    print()
    
    # Execute rollout with CTF agent
    executor = RolloutExecutor()
    
    try:
        print("Executing rollout with CTF agent...")
        print()
        result = await executor.execute(request, agent_type="ctf")
        
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
            print("Trajectory (with CTF thoughts):")
            for step in result.trajectory[:5]:
                print(f"\n  Step {step.step}:")
                thought = step.metadata.get('thought', '')
                if thought:
                    print(f"    💭 Thought: {thought[:80]}...")
                print(f"    🎯 Action: {step.action[:80]}...")
                print(f"    📝 Observation: {step.observation[:80]}...")
                print(f"    Reward: {step.reward}, Done: {step.done}")
            
            if len(result.trajectory) > 5:
                print(f"\n  ... and {len(result.trajectory) - 5} more steps")
        
        # Print full result as dict
        print("\n" + "=" * 70)
        print("Full Rollout Result (dict format)")
        print("=" * 70)
        result_dict = result.model_dump()
        # Truncate long trajectory items for readability
        if result_dict.get('trajectory'):
            for step in result_dict['trajectory']:
                for key in ['action', 'observation', 'thought']:
                    if key in step.get('metadata', {}) and len(step['metadata'][key]) > 200:
                        step['metadata'][key] = step['metadata'][key][:200] + '...'
                if 'observation' in step and len(step['observation']) > 200:
                    step['observation'] = step['observation'][:200] + '...'
                if 'action' in step and len(step['action']) > 200:
                    step['action'] = step['action'][:200] + '...'
        print(json.dumps(result_dict, indent=2, default=str))
        print()
        
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
    exit_code = asyncio.run(test_ctf_agent())
    sys.exit(exit_code)
