#!/usr/bin/env python3
"""
Test script for local Qwen 2.5 1.5B model.

This tests the InferenceEngineClientWrapper with the local model.

Usage:
    python test_local_model.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ez_llm_server.client import InferenceEngineClientWrapper


async def test_local_model():
    """Test the local Qwen 2.5 1.5B model."""
    
    print("=" * 60)
    print("Testing Local Qwen 2.5 1.5B Model")
    print("=" * 60)
    print()
    
    # Initialize client with local model name
    client = InferenceEngineClientWrapper(
        endpoint="http://127.0.0.1:8001",
        model_name="qwen2.5-1.5b",  # Matches --served-model-name in start script
    )
    
    print(f"✓ Client initialized")
    print(f"  Endpoint: {client.endpoint}")
    print(f"  Model: {client.model_name}")
    print()
    
    # Test prompt
    engine_input = {
        "prompts": [[
            {
                "role": "user",
                "content": "Write a Python script in bash format to print 'Hello World'"
            }
        ]],
        "sampling_params": {
            "max_tokens": 200,
            "temperature": 0.7,
        }
    }
    
    print("Input:")
    print(f"  Prompt: {engine_input['prompts'][0][0]['content']}")
    print(f"  Max tokens: {engine_input['sampling_params']['max_tokens']}")
    print(f"  Temperature: {engine_input['sampling_params']['temperature']}")
    print()
    
    print("Generating response...")
    print()
    
    try:
        engine_output = await client.generate(engine_input)
        
        response = engine_output["responses"][0]
        stop_reason = engine_output["stop_reasons"][0]
        
        print("=" * 60)
        print("Response:")
        print("=" * 60)
        print(response)
        print()
        print("=" * 60)
        print(f"Stop reason: {stop_reason}")
        print("=" * 60)
        print()
        print("✓ Test completed successfully!")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        print()
        print("Make sure vLLM server is running:")
        print("  cd ez_llm_server/server")
        print("  bash start_vllm.sh")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(test_local_model())
    sys.exit(exit_code)
