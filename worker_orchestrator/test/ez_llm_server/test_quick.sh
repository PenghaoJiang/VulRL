#!/bin/bash
# Quick test for vLLM server - shows raw responses

echo "Testing vLLM server at http://127.0.0.1:8001"
echo ""

# Test 1: Health
echo "1. Testing /health endpoint..."
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" http://127.0.0.1:8001/health)
echo "$RESPONSE"
echo ""

# Test 2: Models
echo "2. Testing /v1/models endpoint..."
RESPONSE=$(curl -s -w "\nHTTP_CODE:%{http_code}" http://127.0.0.1:8001/v1/models)
echo "$RESPONSE"
echo ""

# Test 3: Chat (with correct model name)
echo "3. Testing /v1/chat/completions endpoint..."
curl -s http://127.0.0.1:8001/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "qwen2.5-1.5b",
    "messages": [{"role": "user", "content": "Say hello in 5 words"}],
    "max_tokens": 20
  }'
echo ""
echo ""

echo "✓ Tests completed!"
