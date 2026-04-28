#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ORCH_DIR="$REPO_ROOT/worker_orchestrator"
PID_FILE="$ORCH_DIR/logs/worker_router.pid"

if [ -f "$PID_FILE" ]; then
  PID="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
    kill "$PID"
    sleep 2
    if kill -0 "$PID" 2>/dev/null; then
      kill -9 "$PID" 2>/dev/null || true
    fi
    echo "Stopped Worker Router PID $PID"
  else
    echo "PID file exists but process is not running."
  fi
  rm -f "$PID_FILE"
else
  echo "No Worker Router PID file found."
fi

WORKER_PIDS="$(ps aux | grep 'worker_unit/main.py' | grep -v grep | awk '{print $2}')"
if [ -n "$WORKER_PIDS" ]; then
  echo "$WORKER_PIDS" | xargs kill -9 2>/dev/null || true
  echo "Stopped worker units."
fi
