#!/bin/bash
# Simple test script for vLLM server HTTP endpoints

echo "Testing vLLM server..."
echo ""

# Test health endpoint
echo "1. Testing /health endpoint..."
curl -s http://127.0.0.1:8001/health | python3 -m json.tool
echo ""
echo ""

# Test models endpoint
echo "2. Testing /v1/models endpoint..."
curl -s http://127.0.0.1:8001/v1/models | python3 -m json.tool
echo ""
echo ""

# Test chat completions
echo "3. Testing /v1/chat/completions endpoint..."
curl -s http://127.0.0.1:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "Qwen/Qwen2.5-7B-Instruct",
    "messages": [
      {"role": "user", "content": "Write a Python script to print Hello World"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
  }' | python3 -m json.tool

echo ""
