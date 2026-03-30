#!/bin/bash
# Start Worker Router and Redis

set -e

echo "Starting VulRL Worker Router..."
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

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
echo "✓ Virtual environment activated"
echo ""

# Cleanup before starting
echo "Cleanup (Redis + Worker Units)..."

# Stop all running worker units
echo "  - Stopping all worker units..."
WORKER_PIDS=$(ps aux | grep "worker_unit/main.py" | grep -v grep | awk '{print $2}')
if [ -n "$WORKER_PIDS" ]; then
    echo "$WORKER_PIDS" | xargs kill -9 2>/dev/null || true
    echo "    ✓ Stopped $(echo "$WORKER_PIDS" | wc -l) worker(s)"
else
    echo "    ℹ No workers running"
fi

# Empty Redis database (if Redis is running)
echo "  - Flushing Redis database..."
if redis-cli ping > /dev/null 2>&1; then
    redis-cli FLUSHALL > /dev/null 2>&1
    echo "    ✓ Redis database cleared"
else
    echo "    ℹ Redis not running yet, will start fresh"
fi

# Clean up old worker logs
echo "  - Cleaning old worker logs..."
rm -f logs/worker_auto_*.log 2>/dev/null || true
echo "    ✓ Old logs removed"
echo ""

# Verify uvicorn is installed
if ! python -m uvicorn --version &> /dev/null; then
    echo "✗ uvicorn not installed in venv!"
    echo ""
    echo "Please run setup:"
    echo "  bash setup.sh"
    exit 1
fi

# Start Redis
echo "Starting Redis..."
if ! redis-cli ping > /dev/null 2>&1; then
    redis-server --daemonize yes
    sleep 2
fi

# Verify Redis is running
if redis-cli ping > /dev/null 2>&1; then
    echo "✓ Redis is running"
else
    echo "✗ Failed to start Redis"
    exit 1
fi
echo ""

# Start FastAPI with uvicorn
echo "✓ Starting Worker Router FastAPI server..."
echo ""
echo "Server: http://0.0.0.0:12345"
echo "API docs: http://localhost:12345/docs"
echo "Logs: logs/worker_router.log"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Run uvicorn
python -m uvicorn worker_router.app:app \
    --host 0.0.0.0 \
    --port 12345 \
    --log-level info

# Note: This will run in foreground. Use Ctrl+C to stop.
# For background: add --reload flag for development or use systemd/supervisor for production
