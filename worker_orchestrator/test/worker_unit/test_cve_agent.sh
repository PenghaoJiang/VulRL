#!/bin/bash
# Single CVE-Bench agent test

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Run: bash setup.sh"
    exit 1
fi

echo "Activating virtual environment..."
# shellcheck source=/dev/null
source venv/bin/activate

# echo "Checking LLM server..."
# if ! curl -s http://127.0.0.1:8001/health > /dev/null 2>&1; then
#     echo "LLM server not running. Start: bash start_llm_server.sh"
#     exit 1
# fi

export OPENAI_API_KEY="dummy-key-for-local-vllm"

python test/worker_unit/test_cve_agent.py
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Done."
else
    exit $EXIT_CODE
fi
