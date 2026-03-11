#!/bin/bash
#
# Parallel Workers Test - Worker Router + Auto-Scaling
#
# This script tests parallel execution with 2 simultaneous tasks:
# - HTTP communication
# - Auto-scaling (spawning multiple workers)
# - Parallel task execution
# - Active polling for multiple tasks
# - Result retrieval

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "========================================================================"
echo "Parallel Workers Test (2 Tasks Simultaneously)"
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

# 2. Cleanup before test
echo "2. Cleanup (Redis + Worker Units)..."

# Stop all running worker units
echo "  - Stopping all worker units..."
WORKER_PIDS=$(ps aux | grep "worker_unit/main.py" | grep -v grep | awk '{print $2}')
if [ -n "$WORKER_PIDS" ]; then
    echo "$WORKER_PIDS" | xargs kill -9 2>/dev/null || true
    echo -e "    ${GREEN}✓${NC} Stopped $(echo "$WORKER_PIDS" | wc -l) worker(s)"
else
    echo -e "    ${YELLOW}ℹ${NC} No workers running"
fi

# Empty Redis database
echo "  - Flushing Redis database..."
redis-cli FLUSHALL > /dev/null 2>&1
echo -e "    ${GREEN}✓${NC} Redis database cleared"

# Clean up old worker logs
echo "  - Cleaning old worker logs..."
rm -f "$PROJECT_ROOT/logs/worker_auto_*.log" 2>/dev/null || true
echo -e "    ${GREEN}✓${NC} Old logs removed"

echo

# 3. Check prerequisites
echo "3. Checking prerequisites..."

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
    echo "    Start with: cd worker_orchestrator && bash start_llm_server.sh"
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

# Check workers (they will auto-spawn, so just informational)
echo "  - Worker Units..."
WORKERS_STATUS=$(curl -s http://localhost:5000/api/workers/status | python3 -c "import sys, json; data = json.load(sys.stdin); print(f\"{data['active']} active, {data['idle']} idle, {data['busy']} busy\")" 2>/dev/null || echo "0 active, 0 idle, 0 busy")
echo -e "    ${YELLOW}ℹ${NC} Workers: $WORKERS_STATUS"
echo -e "    ${YELLOW}ℹ${NC} (Workers will auto-spawn if needed)"

echo

# 4. Run parallel workers test
echo "4. Running parallel workers test (2 tasks simultaneously)..."
echo

# Use env -i to run in clean environment (avoid proxy issues)
env -i \
    PATH="$PATH" \
    HOME="$HOME" \
    VIRTUAL_ENV="$VIRTUAL_ENV" \
    python test/ez_generator/test_simple.py

exit_code=$?

echo
if [ $exit_code -eq 0 ]; then
    echo -e "${GREEN}✓ Test passed!${NC}"
else
    echo -e "${RED}✗ Test failed with exit code: $exit_code${NC}"
fi

exit $exit_code
