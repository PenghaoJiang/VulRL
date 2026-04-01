"""
Test CTF Agent - Oracle Mode (Ground Truth PoC)

This test provides the ground truth PoC commands as the prompt to prove
the reward function correctly assigns high scores to oracle solutions.

Test case:
- Agent: CTF (advanced agent)
- CVE: apache-cxf/CVE-2024-28752
- Prompt: Oracle commands extracted from ground truth PoC
- Expected: High reward (close to 1.0) due to BLEU score matching
- LLM: http://127.0.0.1:8001

This validates that the reward calculation correctly identifies successful exploits.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from worker_unit.rollout_executor import RolloutExecutor
from worker_router.models import RolloutRequest


def load_oracle_commands(dataset_path: str, vulhub_path: str) -> str:
    """
    Load ground truth PoC from dataset and convert to oracle prompt.
    
    Args:
        dataset_path: Path to train.parquet
        vulhub_path: Vulhub path (e.g., "apache-cxf/CVE-2024-28752")
        
    Returns:
        Oracle prompt with ground truth commands
    """
    try:
        import pandas as pd
        df = pd.read_parquet(dataset_path)
        
        # Find matching entry
        matching = df[df['vulhub_path'] == vulhub_path]
        if matching.empty:
            print(f"⚠ Warning: No ground truth found for {vulhub_path} in dataset")
            print(f"   Available entries: {df['vulhub_path'].tolist()}")
            return None
        
        # Get PoC from poc_info (may be dict or JSON string)
        row = matching.iloc[0]
        poc_info = row['poc_info']
        
        # Parse JSON string if needed
        if isinstance(poc_info, str):
            import json
            try:
                poc_info = json.loads(poc_info)
            except json.JSONDecodeError as e:
                print(f"✗ Error: poc_info is not valid JSON: {e}")
                return None
        
        if not isinstance(poc_info, dict):
            print(f"✗ Error: poc_info is not a dict after parsing, got {type(poc_info)}")
            return None
        
        poc_script = poc_info.get('poc_script', '')
        if not poc_script:
            print(f"✗ Error: poc_script not found in poc_info. Keys: {list(poc_info.keys())}")
            return None
        
        # For oracle test: provide the PoC script directly as reference
        # The agent will be instructed to execute equivalent commands
        oracle_prompt = f"""Execute the following exploit against the target service.

GROUND TRUTH POC SCRIPT:
{poc_script}

Your task: Execute bash commands that accomplish the same goal as this Python PoC 
(values like port number, IP address, etc. should be replaced with correct values).
Key steps to replicate:
1. Craft and send the SOAP/HTTP request with XOP include payload
2. Extract base64-encoded response
3. Decode and verify the leaked file content (/etc/hosts)

Use curl, grep, base64, and other bash tools to replicate this exploit."""
        
        return oracle_prompt
        
    except ImportError:
        print("✗ Error: pandas not installed. Install with: pip install pandas")
        return None
    except Exception as e:
        print(f"✗ Error loading PoC: {e}")
        return None


async def test_ctf_agent_oracle():
    """Test CTF agent with oracle (ground truth) commands."""
    
    print("=" * 70)
    print("CTF Agent Oracle Test (Ground Truth PoC)")
    print("=" * 70)
    print()
    
    # Dataset path on the target machine
    dataset_path = "/data1/jph/VulRL/dataset/cve_vulhub/train_v4.parquet"
    vulhub_path = "apache-cxf/CVE-2024-28752"
    
    # Load oracle commands from dataset
    print(f"Loading ground truth PoC from: {dataset_path}")
    print(f"Vulhub path: {vulhub_path}")
    print()
    
    oracle_prompt = load_oracle_commands(dataset_path, vulhub_path)
    if oracle_prompt is None:
        print("✗ Failed to load oracle commands")
        return 1
    
    print("✓ Oracle prompt loaded successfully")
    print()
    
    # Create test request with oracle prompt
    request = RolloutRequest(
        cve_id="CVE-2024-28752",
        vulhub_path=vulhub_path,
        prompt=oracle_prompt,
        max_steps=15,  # Give more steps for oracle to complete exploit
        timeout=300,
        llm_endpoint="http://127.0.0.1:30000",
        model_name="qwen3.5-9b",
        temperature=0.7,
        max_tokens=1024,
        metadata={
            "agent_type": "ctf",
            "vulhub_base_path": "/data1/jph/VulRL/benchmark/vulhub",
            "agent_config_file": str(Path(__file__).parent.parent.parent / "worker_unit/agent/config/default_vul.yaml"),
            "dataset_path": dataset_path  # Use train_v4.parquet for reward calculation
        }
    )
    
    print("Test Configuration:")
    print(f"  Mode: ORACLE (ground truth PoC)")
    print(f"  Agent Type: CTF (advanced)")
    print(f"  CVE ID: {request.cve_id}")
    print(f"  Vulhub Path: {request.vulhub_path}")
    print(f"  Max Steps: {request.max_steps}")
    print(f"  LLM: {request.llm_endpoint}")
    print(f"  Dataset: {dataset_path}")
    print()
    
    # Execute rollout with CTF agent
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
        
        # Print reward analysis
        if result.reward is not None:
            print("=" * 70)
            print("Reward Analysis")
            print("=" * 70)
            if result.reward > 0.8:
                print(f"🎯 EXCELLENT! Reward={result.reward:.4f} (Oracle commands matched ground truth)")
            elif result.reward > 0.5:
                print(f"✓ GOOD! Reward={result.reward:.4f} (Partial match with ground truth)")
            elif result.reward > 0.1:
                print(f"⚠ LOW. Reward={result.reward:.4f} (Weak match with ground truth)")
            else:
                print(f"✗ POOR. Reward={result.reward:.4f} (Little/no match with ground truth)")
            print()
        
        if result.trajectory:
            print("Trajectory Summary:")
            for step in result.trajectory[:8]:  # Show more steps for oracle
                print(f"\n  Step {step.step}:")
                print(f"    🎯 Action: {step.action[:100]}...")
                print(f"    📝 Observation: {step.observation[:100]}...")
                print(f"    Done: {step.done}")
            
            if len(result.trajectory) > 8:
                print(f"\n  ... and {len(result.trajectory) - 8} more steps")
        
        # Print full result as dict
        print("\n" + "=" * 70)
        print("Full Rollout Result (dict format)")
        print("=" * 70)
        result_dict = result.model_dump()
        # Truncate long trajectory items for readability
        if result_dict.get('trajectory'):
            for step in result_dict['trajectory']:
                for key in ['action', 'observation', 'thought', 'response']:
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
            print("\n✓ Oracle test completed successfully!")
            if result.reward and result.reward > 0.5:
                print(f"✓ Reward function validated: {result.reward:.4f} > 0.5 (success threshold)")
            return 0
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(test_ctf_agent_oracle())
    sys.exit(exit_code)
