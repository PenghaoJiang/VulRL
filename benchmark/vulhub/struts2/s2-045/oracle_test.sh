#!/usr/bin/env bash
set -euo pipefail

cd "${ORACLE_CASE_DIR}"
compose() { docker compose -p "${COMPOSE_PROJECT_NAME}" "$@"; }

struts2_cid=$(compose ps -q struts2)
[[ -n "$struts2_cid" ]] || { echo "[oracle_test] ERROR: struts2 container not found" >&2; exit 2; }

echo "[oracle_test] struts2 container id: $struts2_cid"
echo "[oracle_test] probe: test -f /tmp/exploit.txt inside struts2 container (s2-045 marker)"

if docker exec "$struts2_cid" test -f /tmp/exploit.txt 2>/dev/null; then
  echo "[oracle_test] PASS: marker file exists"
  docker exec "$struts2_cid" ls -la /tmp/exploit.txt 2>/dev/null | head -5 || true
  exit 0
else
  echo "[oracle_test] FAIL: marker file missing"
  docker exec "$struts2_cid" ls -la /tmp 2>/dev/null | head -30 || true
  exit 1
fi
