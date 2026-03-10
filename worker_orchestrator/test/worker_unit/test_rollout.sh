#!/bin/bash
# Test Worker Unit Rollout Executor

set -e

echo "========================================================================"
echo "Testing Worker Unit Rollout Executor"
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
if ! curl -s http://127.0.0.1:8001/health > /dev/null 2>&1; then
    echo "✗ LLM server not running!"
    echo ""
    echo "Please start LLM server first:"
    echo "  bash start_llm_server.sh"
    exit 1
fi
echo "✓ LLM server is running"
echo ""

# Run test
echo "Running worker unit test..."
echo ""

# Run with explicit env clearing (pass clean environment to Python)
env -i PATH="$PATH" \
    VIRTUAL_ENV="$VIRTUAL_ENV" \
    HOME="$HOME" \
    USER="$USER" \
    LANG="$LANG" \
    PWD="$PWD" \
    python test/worker_unit/test_rollout.py

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Test completed!"
else
    echo "✗ Test failed with exit code $EXIT_CODE"
    exit $EXIT_CODE
fi
