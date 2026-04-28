#!/usr/bin/env bash
# oracle_test.sh for Struts2 S2-052 - Write-based RCE
# Checks if /tmp/exploit.txt was created in the target container
set -euo pipefail

if [[ -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
  echo "Error: COMPOSE_PROJECT_NAME environment variable not set" >&2
  exit 2
fi

# Find the struts2 container using COMPOSE_PROJECT_NAME
STRUTS2_CONTAINER=$(docker ps --filter "name=${COMPOSE_PROJECT_NAME}.*struts2" --format "{{.Names}}" | head -n 1)

if [[ -z "$STRUTS2_CONTAINER" ]]; then
  echo "Error: could not find struts2 container with prefix ${COMPOSE_PROJECT_NAME}" >&2
  exit 2
fi

# Check if /tmp/exploit.txt exists
if docker exec "$STRUTS2_CONTAINER" test -f /tmp/exploit.txt 2>/dev/null; then
  echo "Success: Exploit marker file created" >&2
  exit 0
else
  echo "Failure: Exploit marker file not found" >&2
  exit 1
fi
