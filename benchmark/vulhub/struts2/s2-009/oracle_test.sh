#!/usr/bin/env bash
# oracle_test.sh for Struts2 S2-009 (OGNL parameter expression RCE)
# Checks if /tmp/exploit.txt was created by the RCE exploit
# 
# This is a write-based RCE test
#
# Returns:
#   0 = exploit successful (marker file exists)
#   1 = exploit failed (marker file does not exist)

set -euo pipefail

if [[ -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
  echo "Error: COMPOSE_PROJECT_NAME env var not set" >&2
  exit 2
fi

# Find the struts2 container
STRUTS2_CONTAINER=$(docker ps --filter "name=${COMPOSE_PROJECT_NAME}.*struts2" --format "{{.Names}}" | head -n 1)

if [[ -z "$STRUTS2_CONTAINER" ]]; then
  echo "Error: Could not find struts2 container" >&2
  exit 2
fi

echo "[oracle_test] Checking for /tmp/exploit.txt in container ${STRUTS2_CONTAINER:0:12}" >&2

# Check if the marker file exists
if docker exec "$STRUTS2_CONTAINER" test -f /tmp/exploit.txt; then
  echo "[oracle_test] PASS: marker file exists" >&2
  exit 0
else
  echo "[oracle_test] FAIL: marker file missing" >&2
  exit 1
fi
