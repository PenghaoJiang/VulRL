#!/bin/bash
# Stop all services

echo "Stopping all VulRL services..."
echo ""

# Stop Worker Router
echo "1. Stopping Worker Router..."
bash stop_worker_router.sh
echo ""

# Stop LLM Server
echo "2. Stopping vLLM server..."
bash stop_llm_server.sh
echo ""

# Optionally stop Redis
echo "3. Redis status..."
if redis-cli ping > /dev/null 2>&1; then
    echo "✓ Redis is still running (shared service)"
    echo ""
    read -p "Stop Redis too? (y/N): " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        redis-cli shutdown
        echo "✓ Redis stopped"
    fi
else
    echo "✓ Redis is not running"
fi

echo ""
echo "All services stopped"
