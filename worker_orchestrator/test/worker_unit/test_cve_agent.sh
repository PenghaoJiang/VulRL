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

export LLM_PORT=12345
export LLM_MODEL=qwen2.5-7b-instruct
echo "Checking LLM server (LLM_PORT=${LLM_PORT})..."
if ! curl -s "http://127.0.0.1:${LLM_PORT}/health" > /dev/null 2>&1; then
    echo "LLM server not running at http://127.0.0.1:${LLM_PORT}/health"
    echo "Start the server (e.g. bash start_llm_server.sh) or set LLM_PORT=12345 to match your vLLM port."
    exit 1
fi

export OPENAI_API_KEY="dummy-key-for-local-vllm"

python test/worker_unit/test_cve_agent.py
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "Done."
else
    exit $EXIT_CODE
fi
