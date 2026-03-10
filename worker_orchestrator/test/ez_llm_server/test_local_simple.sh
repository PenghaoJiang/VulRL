#!/bin/bash
# Simple test for local Qwen model via HTTP

echo "Testing local Qwen 2.5 1.5B model..."
echo ""

# Test health endpoint
echo "1. Testing /health endpoint..."
curl -s http://127.0.0.1:8001/health | python -m json.tool
echo ""
echo ""

# Test models endpoint
echo "2. Testing /v1/models endpoint..."
curl -s http://127.0.0.1:8001/v1/models | python -m json.tool
echo ""
echo ""

# Test chat completions with local model
echo "3. Testing /v1/chat/completions endpoint..."
curl -s http://127.0.0.1:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-1.5b",
    "messages": [
      {"role": "user", "content": "Write a Python script to print Hello World"}
    ],
    "max_tokens": 100,
    "temperature": 0.7
  }' | python -m json.tool

echo ""
