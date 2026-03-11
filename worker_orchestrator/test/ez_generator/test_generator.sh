#!/bin/bash
#
# Test script for EzVulRL Generator
#
# This script tests the ez_generator by:
# 1. Checking prerequisites (Worker Router, Workers, LLM server, Redis)
# 2. Running the test_generator.py test suite
#
# Prerequisites:
#   - Worker Router running (bash worker_orchestrator/start_worker_router.sh)
#   - Worker Unit running (bash worker_orchestrator/start_worker.sh)
#   - LLM server running (bash worker_orchestrator/start_llm_server.sh)
#   - Redis running (systemctl start redis)

set -e  # Exit on error

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "========================================================================"
echo "EzVulRL Generator Test"
echo "========================================================================"
echo

# Change to project root
cd "$PROJECT_ROOT"

# 1. Activate venv
echo "1. Activating virtual environment..."
if [ ! -d "venv" ]; then
    echo -e "${RED}✗ Virtual environment not found: $PROJECT_ROOT/venv${NC}"
    echo "  Please run: bash setup.sh"
    exit 1
fi

source venv/bin/activate
echo -e "${GREEN}✓${NC} Virtual environment activated"
echo

# 2. Check prerequisites
echo "2. Checking prerequisites..."

# Check Worker Router
echo "  - Worker Router (http://localhost:5000)..."
if curl -s -f http://localhost:5000/health > /dev/null 2>&1; then
    echo -e "    ${GREEN}✓${NC} Worker Router is running"
else
    echo -e "    ${RED}✗${NC} Worker Router is not running"
    echo "    Start with: cd worker_orchestrator && bash start_worker_router.sh"
    exit 1
fi

# Check LLM server
echo "  - LLM server (http://localhost:8001)..."
if curl -s -f http://localhost:8001/health > /dev/null 2>&1; then
    echo -e "    ${GREEN}✓${NC} LLM server is running"
else
    echo -e "    ${RED}✗${NC} LLM server is not running"
    echo "    Start with: bash worker_orchestrator/start_llm_server.sh"
    exit 1
fi

# Check Redis
echo "  - Redis (localhost:6379)..."
if redis-cli ping > /dev/null 2>&1; then
    echo -e "    ${GREEN}✓${NC} Redis is running"
else
    echo -e "    ${RED}✗${NC} Redis is not running"
    echo "    Start with: sudo systemctl start redis"
    exit 1
fi

# Check workers
echo "  - Worker Units..."
WORKERS_STATUS=$(curl -s http://localhost:5000/api/workers/status | python3 -c "import sys, json; data = json.load(sys.stdin); print(f\"{data['active']} active, {data['idle']} idle, {data['busy']} busy\")")
echo -e "    ${GREEN}✓${NC} Workers: $WORKERS_STATUS"

echo

# 3. Run test
echo "3. Running test suite..."
echo

# Use env -i to run in clean environment (avoid proxy issues)
env -i \
    PATH="$PATH" \
    HOME="$HOME" \
    VIRTUAL_ENV="$VIRTUAL_ENV" \
    python test/ez_generator/test_generator.py

exit_code=$?

echo
if [ $exit_code -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
else
    echo -e "${RED}✗ Tests failed with exit code: $exit_code${NC}"
fi

exit $exit_code
