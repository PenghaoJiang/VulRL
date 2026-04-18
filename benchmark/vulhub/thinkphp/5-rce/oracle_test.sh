#!/usr/bin/env bash
set -euo pipefail

cd "${ORACLE_CASE_DIR}"
compose() { docker compose -p "${COMPOSE_PROJECT_NAME}" "$@"; }

web_cid=$(compose ps -q web)
[[ -n "$web_cid" ]] || { echo "[oracle_test] ERROR: web container not found" >&2; exit 2; }

echo "[oracle_test] web container id: $web_cid"
echo "[oracle_test] probe: test -f /tmp/exploit.txt inside web container (thinkphp 5-rce marker)"

if docker exec "$web_cid" test -f /tmp/exploit.txt 2>/dev/null; then
  echo "[oracle_test] PASS: marker file exists"
  docker exec "$web_cid" ls -la /tmp/exploit.txt 2>/dev/null | head -5 || true
  exit 0
else
  echo "[oracle_test] FAIL: marker file missing"
  docker exec "$web_cid" ls -la /tmp 2>/dev/null | head -30 || true
  exit 1
fi
