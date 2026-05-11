#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ORCH_DIR="$REPO_ROOT/worker_orchestrator"
SERVER_LOG_DIR="$REPO_ROOT/logs/server"
ROUTER_LOG_DIR="$ORCH_DIR/logs"

mkdir -p "$SERVER_LOG_DIR" "$ROUTER_LOG_DIR"

RUN_STAMP="${RUN_STAMP:-$(date +%Y%m%d_%H%M%S)}"
STDOUT_LOG="$SERVER_LOG_DIR/worker_router_stdout_${RUN_STAMP}.log"
LATEST_STDOUT_LOG="$SERVER_LOG_DIR/worker_router_stdout_latest.log"
PID_FILE="$ROUTER_LOG_DIR/worker_router.pid"

if [ ! -x "$ORCH_DIR/venv/bin/python" ]; then
  echo "worker_orchestrator venv not found."
  echo "Run: bash $ORCH_DIR/setup.sh"
  exit 1
fi

if ! command -v redis-server >/dev/null 2>&1; then
  echo "redis-server not found on PATH."
  exit 1
fi

if ! command -v redis-cli >/dev/null 2>&1; then
  echo "redis-cli not found on PATH."
  exit 1
fi

if [ -f "$PID_FILE" ]; then
  OLD_PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$OLD_PID" ] && kill -0 "$OLD_PID" 2>/dev/null; then
    echo "Worker Router already running with PID $OLD_PID"
    echo "PID file: $PID_FILE"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

ln -sfn "$STDOUT_LOG" "$LATEST_STDOUT_LOG"

echo "Cleaning up stale worker processes..."
WORKER_PIDS="$(ps aux | grep 'worker_unit/main.py' | grep -v grep | awk '{print $2}')"
if [ -n "$WORKER_PIDS" ]; then
  echo "$WORKER_PIDS" | xargs kill -9 2>/dev/null || true
fi

echo "Starting Redis if needed..."
if ! redis-cli ping >/dev/null 2>&1; then
  redis-server --daemonize yes
  sleep 2
fi

if ! redis-cli ping >/dev/null 2>&1; then
  echo "Failed to start Redis."
  exit 1
fi

echo "Flushing Redis for a clean run..."
redis-cli FLUSHALL >/dev/null

echo "Cleaning old worker logs..."
rm -f "$ROUTER_LOG_DIR"/worker_auto_*.log 2>/dev/null || true

cd "$ORCH_DIR"

echo "Starting Worker Router on http://127.0.0.1:12345 ..."
nohup "$ORCH_DIR/venv/bin/python" -m uvicorn worker_router.app:app \
  --host 0.0.0.0 \
  --port 12345 \
  --log-level info >> "$STDOUT_LOG" 2>&1 &

ROUTER_PID=$!
echo "$ROUTER_PID" > "$PID_FILE"
sleep 2

if ! kill -0 "$ROUTER_PID" 2>/dev/null; then
  echo "Worker Router failed to start."
  echo "Stdout log: $STDOUT_LOG"
  exit 1
fi

echo "============================================================"
echo "Worker Router started"
echo "============================================================"
echo "PID: $ROUTER_PID"
echo "PID file: $PID_FILE"
echo "Router stdout log: $STDOUT_LOG"
echo "Router app log: $ROUTER_LOG_DIR/worker_router.log"
echo "Worker logs: $ROUTER_LOG_DIR/worker_auto_*.log"
echo "Health check: curl http://127.0.0.1:12345/health"
echo "============================================================"
