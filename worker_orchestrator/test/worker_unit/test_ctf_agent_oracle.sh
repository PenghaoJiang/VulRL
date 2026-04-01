#!/bin/bash
# Test CTF Agent - Oracle Mode (Ground Truth PoC)
# 
# This test provides the ground truth PoC as the prompt to validate
# that the reward function correctly assigns high scores to oracle solutions.

set -e

echo "========================================================================"
echo "Testing CTF Agent - ORACLE MODE (Ground Truth PoC)"
echo "========================================================================"
echo ""

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "✗ Virtual environment not found!"
    echo ""
    echo "Please run setup first:"
    echo "  bash setup.sh"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if LLM server is running
echo "Checking LLM server..."
LLM_PORT=30000
if ! curl -s http://127.0.0.1:$LLM_PORT/health > /dev/null 2>&1; then
    echo "✗ LLM server not running on port $LLM_PORT!"
    echo ""
    echo "Please start LLM server first:"
    echo "  bash start_llm_server.sh"
    exit 1
fi
echo "✓ LLM server is running on port $LLM_PORT"
echo ""

# Check if dataset exists
DATASET_PATH="/data1/jph/VulRL/dataset/cve_vulhub/train_v4.parquet"
if [ ! -f "$DATASET_PATH" ]; then
    echo "✗ Dataset not found: $DATASET_PATH"
    echo ""
    echo "Please ensure train_v4.parquet exists at the specified location"
    exit 1
fi
echo "✓ Dataset found: $DATASET_PATH"
echo ""

# Run oracle test
echo "Running CTF agent oracle test..."
echo ""

# Set dummy OpenAI API key for local vLLM server
export OPENAI_API_KEY="dummy-key-for-local-vllm"

python test/worker_unit/test_ctf_agent_oracle.py

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Oracle test completed!"
else
    echo "✗ Oracle test failed with exit code $EXIT_CODE"
    exit $EXIT_CODE
fi
