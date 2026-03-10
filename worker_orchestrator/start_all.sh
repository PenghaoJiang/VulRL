#!/bin/bash
# Start all services (Redis, Worker Router, LLM Server)

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "========================================="
echo "Starting VulRL Worker Orchestration"
echo "========================================="
echo ""

# 1. Start Redis
echo "1. Starting Redis..."
if redis-cli ping > /dev/null 2>&1; then
    echo "✓ Redis is already running"
else
    redis-server --daemonize yes
    sleep 2
    if redis-cli ping > /dev/null 2>&1; then
        echo "✓ Redis started successfully"
    else
        echo "✗ Failed to start Redis"
        exit 1
    fi
fi
echo ""

# 2. Start LLM Server (in background)
echo "2. Starting vLLM server in background..."
bash start_llm_server.sh > logs/llm_server.log 2>&1 &
LLM_PID=$!
echo "✓ vLLM server started (PID: $LLM_PID)"
echo "  Logs: logs/llm_server.log"
echo "  Waiting for server to be ready..."
sleep 10  # Give vLLM time to start
echo ""

# 3. Start Worker Router (foreground)
echo "3. Starting Worker Router..."
echo "  Server: http://localhost:5000"
echo "  API docs: http://localhost:5000/docs"
echo ""
echo "Press Ctrl+C to stop all services"
echo ""

# Trap Ctrl+C to stop all services
trap 'echo ""; echo "Stopping all services..."; bash stop_all.sh; exit' INT

# Start Worker Router in foreground
bash start_worker_router.sh
