#!/bin/bash
# Stop Worker Router

echo "Stopping VulRL Worker Router..."

# Kill uvicorn process
pkill -f "uvicorn worker_router.app:app" || echo "No Worker Router process found"

echo "Worker Router stopped"
echo ""
echo "Note: Redis is still running (shared service)"
echo "To stop Redis: redis-cli shutdown"