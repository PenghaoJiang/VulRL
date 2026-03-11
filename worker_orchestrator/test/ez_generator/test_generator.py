"""
Test script for EzVulRL Generator.

This tests the generator in standalone mode, without full SkyRL integration.
It directly calls the vulrl_agent_loop() method to verify the HTTP communication
and polling mechanism.
"""

import asyncio
import sys
from pathlib import Path

# Add paths
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))
sys.path.insert(0, str(project_root.parent / "SkyRL" / "skyrl-train"))

from ez_generator import EzVulRLGenerator, WorkerRouterClient


async def test_worker_router_client():
    """Test the WorkerRouterClient directly."""
    print("=" * 70)
    print("Test 1: Worker Router Client")
    print("=" * 70)
    
    client = WorkerRouterClient(base_url="http://localhost:5000")
    
    try:
        # Check health
        print("\n1. Checking Worker Router health...")
        healthy = await client.check_health()
        if healthy:
            print("✓ Worker Router is healthy")
        else:
            print("✗ Worker Router is not healthy")
            return False
        
        # Check workers status
        print("\n2. Checking workers status...")
        workers_status = await client.check_workers_health()
        print(f"✓ Workers: {workers_status['total']} total, {workers_status['active']} active")
        
        if workers_status['active'] == 0:
            print("⚠ No active workers available!")
            return False
        
        # Submit a test rollout
        print("\n3. Submitting test rollout...")
        from worker_router.models import RolloutRequest
        
        request = RolloutRequest(
            cve_id="CVE-2024-28752",
            vulhub_path="apache-cxf/CVE-2024-28752",
            prompt="write a hello world script at /tmp/workspace/",
            llm_endpoint="http://localhost:8001",
            model_name="qwen2.5-1.5b",
            max_steps=5,
            temperature=0.7,
            max_tokens=512,
            metadata={"test": "ez_generator_test"}
        )
        
        task_id = await client.submit_rollout(request)
        print(f"✓ Task submitted: {task_id}")
        
        # Wait for completion
        print("\n4. Waiting for rollout to complete...")
        result = await client.wait_for_rollout(
            task_id,
            timeout=300.0,
            poll_interval=5.0,  # Faster polling for test
            verbose=True
        )
        
        print("\n" + "=" * 70)
        print("Rollout Result")
        print("=" * 70)
        print(f"Status: {result.status}")
        print(f"Reward: {result.reward}")
        print(f"Success: {result.success}")
        print(f"Duration: {result.duration:.2f}s" if result.duration else "Duration: N/A")
        print(f"Steps: {len(result.trajectory or [])}")
        
        if result.trajectory:
            print("\nTrajectory:")
            for step in result.trajectory[:3]:  # Show first 3 steps
                print(f"  Step {step.step}:")
                print(f"    Action: {step.action[:100]}...")
                print(f"    Observation: {step.observation[:100]}...")
                print(f"    Reward: {step.reward}")
        
        print("\n✓ Test completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
    finally:
        await client.close()


async def test_generator_mock():
    """
    Test the generator with mock SkyRL interface.
    
    This tests the generator's ability to process inputs and return
    outputs in the expected format, without full SkyRL integration.
    """
    print("\n" + "=" * 70)
    print("Test 2: EzVulRL Generator (Mock SkyRL Interface)")
    print("=" * 70)
    
    # Create mock tokenizer (simplified)
    class MockTokenizer:
        def encode(self, text, add_special_tokens=False):
            # Simple word-based tokenization
            return [hash(word) % 50000 for word in text.split()]
        
        def apply_chat_template(self, messages, add_generation_prompt=False, tokenize=True):
            # Concatenate all messages
            text = " ".join(msg.get("content", "") for msg in messages)
            return self.encode(text) if tokenize else text
    
    # Create mock configs (simplified)
    class MockConfig:
        def __init__(self):
            self.sampling_params = type('obj', (object,), {
                'max_generate_length': 512,
                'temperature': 0.7
            })
            self.max_input_length = 2048
            self.backend = "vllm"
    
    class MockSkyRLGymConfig:
        pass
    
    class MockInferenceEngineClient:
        pass
    
    class MockBatchMetadata:
        def __init__(self):
            self.global_step = 0
            self.training_phase = "train"
    
    try:
        # Initialize generator
        print("\n1. Initializing generator...")
        generator = EzVulRLGenerator(
            generator_cfg=MockConfig(),
            skyrl_gym_cfg=MockSkyRLGymConfig(),
            inference_engine_client=MockInferenceEngineClient(),
            tokenizer=MockTokenizer(),
            model_name="qwen2.5-1.5b",
            worker_router_url="http://localhost:5000",
            llm_endpoint="http://localhost:8001",
            llm_model_name="qwen2.5-1.5b",
            polling_config={
                "timeout": 300.0,
                "poll_interval": 5.0,
                "verbose": True,
            }
        )
        print("✓ Generator initialized")
        
        # Test vulrl_agent_loop
        print("\n2. Testing vulrl_agent_loop...")
        result = await generator.vulrl_agent_loop(
            prompt="write a hello world script at /tmp/workspace/",
            env_extras={
                "cve_id": "CVE-2024-28752",
                "vulhub_path": "apache-cxf/CVE-2024-28752",
                "max_steps": 5,
            },
            max_tokens=512,
            max_input_length=2048,
            sampling_params={"temperature": 0.7},
            trajectory_id="test_trajectory_001",
            batch_metadata=MockBatchMetadata(),
        )
        
        response_ids, reward, stop_reason, loss_mask, prompt_ids, rollout_logprobs = result
        
        print("\n" + "=" * 70)
        print("Generator Output")
        print("=" * 70)
        print(f"Response IDs length: {len(response_ids) if response_ids else 0}")
        print(f"Reward: {reward}")
        print(f"Stop reason: {stop_reason}")
        print(f"Loss mask length: {len(loss_mask) if loss_mask else 0}")
        print(f"Prompt IDs length: {len(prompt_ids) if prompt_ids else 0}")
        
        if response_ids and loss_mask:
            print(f"✓ Valid output: {len(response_ids)} response tokens, reward={reward}")
        else:
            print("⚠ Output is None (trajectory generation may have failed)")
        
        # Cleanup
        await generator.cleanup()
        
        print("\n✓ Test completed successfully!")
        return True
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """Run all tests."""
    print("=" * 70)
    print("EzVulRL Generator Test Suite")
    print("=" * 70)
    print()
    print("Prerequisites:")
    print("  - Worker Router running on http://localhost:5000")
    print("  - At least one worker unit running")
    print("  - LLM server running on http://localhost:8001")
    print("  - Redis running on localhost:6379")
    print()
    
    # Test 1: Client
    success1 = await test_worker_router_client()
    
    # Test 2: Generator
    if success1:
        success2 = await test_generator_mock()
    else:
        print("\n⚠ Skipping Test 2 due to Test 1 failure")
        success2 = False
    
    # Summary
    print("\n" + "=" * 70)
    print("Test Summary")
    print("=" * 70)
    print(f"Test 1 (Client): {'✓ PASS' if success1 else '✗ FAIL'}")
    print(f"Test 2 (Generator): {'✓ PASS' if success2 else '✗ FAIL'}")
    print()
    
    if success1 and success2:
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
