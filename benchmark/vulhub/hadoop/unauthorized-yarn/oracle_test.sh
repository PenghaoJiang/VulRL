#!/usr/bin/env bash
set -euo pipefail

cd "${ORACLE_CASE_DIR}"
compose() { docker compose -p "${COMPOSE_PROJECT_NAME}" "$@"; }

nodemanager_cid=$(compose ps -q nodemanager)
[[ -n "$nodemanager_cid" ]] || { echo "[oracle_test] ERROR: nodemanager container not found" >&2; exit 2; }

echo "[oracle_test] nodemanager container id: $nodemanager_cid"
echo "[oracle_test] probe: test -f /tmp/exploit.txt inside nodemanager container (unauthorized-yarn marker)"

if docker exec "$nodemanager_cid" test -f /tmp/exploit.txt 2>/dev/null; then
  echo "[oracle_test] PASS: marker file exists"
  docker exec "$nodemanager_cid" ls -la /tmp/exploit.txt 2>/dev/null | head -5 || true
  exit 0
else
  echo "[oracle_test] FAIL: marker file missing"
  docker exec "$nodemanager_cid" ls -la /tmp 2>/dev/null | head -30 || true
  exit 1
fi
