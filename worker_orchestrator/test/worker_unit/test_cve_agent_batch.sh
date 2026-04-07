#!/bin/bash
# Sequential CVE-Bench batch test (optional CVE ids as args)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

if [ ! -d "venv" ]; then
    echo "Virtual environment not found. Run: bash setup.sh"
    exit 1
fi

# shellcheck source=/dev/null
source venv/bin/activate

export LLM_PORT=12345
export LLM_MODEL=qwen2.5-7b-instruct
if ! curl -s "http://127.0.0.1:${LLM_PORT}/health" > /dev/null 2>&1; then
    echo "LLM server not running at http://127.0.0.1:${LLM_PORT}/health (set LLM_PORT if needed)"
    exit 1
fi

export OPENAI_API_KEY="dummy-key-for-local-vllm"

python test/worker_unit/test_cve_agent_batch.py "$@"
EXIT_CODE=$?
exit $EXIT_CODE
