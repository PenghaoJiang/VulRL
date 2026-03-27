#!/usr/bin/env python3
"""
Test InferenceEngineClientWrapper with user's exact prompt.

Prompt: "write return a python script in bash format to print 'Hello World'"

Usage:
    source ../../venv/bin/activate
    python test_generate.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent directories to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ez_llm_server.client import InferenceEngineClientWrapper


async def test_generate():
    """Test generate() with user's exact prompt."""
    
    print("=" * 70)
    print("Testing InferenceEngineClientWrapper.generate()")
    print("(Mimics SkyRL's InferenceEngineClient interface)")
    print("=" * 70)
    print()
    
    # Initialize client
    client = InferenceEngineClientWrapper(
        endpoint="http://127.0.0.1:8001",
        model_name="qwen2.5-1.5b",
    )
    
    print(f"✓ Client initialized")
    print(f"  Endpoint: {client.endpoint}")
    print(f"  Model: {client.model_name}")
    print()
    
    # User's exact prompt
    test_prompt = "write return a python script in bash format to print 'Hello World'"
    
    engine_input = {
        "prompts": [[
            {"role": "user", "content": test_prompt}
        ]],
        "sampling_params": {
            "max_tokens": 200,
            "temperature": 0.7,
        }
    }
    
    print("Input:")
    print(f"  Prompt: {test_prompt}")
    print(f"  Max tokens: 200")
    print(f"  Temperature: 0.7")
    print()
    
    print("Calling client.generate()...")
    print()
    
    try:
        # Same interface as SkyRL's InferenceEngineClient.generate()
        engine_output = await client.generate(engine_input)
        
        response = engine_output["responses"][0]
        stop_reason = engine_output["stop_reasons"][0]
        
        print("=" * 70)
        print("LLM Response:")
        print("=" * 70)
        print(response)
        print()
        print("=" * 70)
        print(f"Stop reason: {stop_reason}")
        print("=" * 70)
        print()
        print("✓ Test completed successfully!")
        print()
        print("This client uses the SAME interface as SkyRL's InferenceEngineClient!")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        import traceback
        traceback.print_exc()
        print()
        print("Make sure vLLM server is running:")
        print("  bash start_llm_server.sh")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(test_generate())
    sys.exit(exit_code)
