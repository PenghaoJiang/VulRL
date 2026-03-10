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

# Verify uvicorn is installed
if ! python -m uvicorn --version &> /dev/null; then
    echo "✗ uvicorn not installed in venv!"
    echo ""
    echo "Please run setup:"
    echo "  bash setup.sh"
    exit 1
fi

# Check if Redis is already running
if redis-cli ping > /dev/null 2>&1; then
    echo "✓ Redis is already running"
else
    echo "Starting Redis..."
    redis-server --daemonize yes
    sleep 2
    
    # Verify Redis started
    if redis-cli ping > /dev/null 2>&1; then
        echo "✓ Redis started successfully"
    else
        echo "✗ Failed to start Redis"
        exit 1
    fi
fi

# Start FastAPI with uvicorn
echo "✓ Starting Worker Router FastAPI server..."
echo ""
echo "Server: http://0.0.0.0:5000"
echo "API docs: http://localhost:5000/docs"
echo "Logs: logs/worker_router.log"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Run uvicorn
python -m uvicorn worker_router.app:app \
    --host 0.0.0.0 \
    --port 5000 \
    --log-level info

# Note: This will run in foreground. Use Ctrl+C to stop.
# For background: add --reload flag for development or use systemd/supervisor for production
