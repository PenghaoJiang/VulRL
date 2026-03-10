#!/bin/bash
# Stop vLLM server

echo "Stopping vLLM LLM Server..."

# Kill vLLM process
pkill -f "vllm.entrypoints.openai.api_server" || echo "No vLLM server process found"

echo "vLLM server stopped"
