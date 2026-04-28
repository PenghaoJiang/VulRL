#!/usr/bin/env bash
# oracle_flag_setup.sh for Struts2 S2-053 - Read-based RCE
# Creates the secret flag file in the target container
set -euo pipefail

if [[ -z "${ORACLE_FLAG:-}" ]]; then
  echo "Error: ORACLE_FLAG environment variable not set" >&2
  exit 1
fi

if [[ -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
  echo "Error: COMPOSE_PROJECT_NAME environment variable not set" >&2
  exit 1
fi

# Find the struts2 container using COMPOSE_PROJECT_NAME
STRUTS2_CONTAINER=$(docker ps --filter "name=${COMPOSE_PROJECT_NAME}.*struts2" --format "{{.Names}}" | head -n 1)

if [[ -z "$STRUTS2_CONTAINER" ]]; then
  echo "Error: could not find struts2 container with prefix ${COMPOSE_PROJECT_NAME}" >&2
  exit 1
fi

# Create the flag file
docker exec "$STRUTS2_CONTAINER" bash -c "echo '$ORACLE_FLAG' > /tmp/secret_flag.txt"

echo "Flag file created successfully in $STRUTS2_CONTAINER" >&2
