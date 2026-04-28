#!/usr/bin/env bash
# oracle_flag_setup.sh for Struts2 S2-032 (OGNL RCE)
# Creates a secret flag file in the target container for read-based oracle testing
# Expects env var: ORACLE_FLAG (e.g., flag_abc123xyz...)

set -euo pipefail

if [[ -z "${ORACLE_FLAG:-}" ]]; then
  echo "Error: ORACLE_FLAG env var not set" >&2
  exit 1
fi

if [[ -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
  echo "Error: COMPOSE_PROJECT_NAME env var not set" >&2
  exit 1
fi

# Find the struts2 container
STRUTS2_CONTAINER=$(docker ps --filter "name=${COMPOSE_PROJECT_NAME}.*struts2" --format "{{.Names}}" | head -n 1)

if [[ -z "$STRUTS2_CONTAINER" ]]; then
  echo "Error: Could not find struts2 container" >&2
  exit 1
fi

echo "Setting up flag in struts2 container: $STRUTS2_CONTAINER" >&2

# Create the flag file in the struts2 container
docker exec "$STRUTS2_CONTAINER" sh -c "echo '$ORACLE_FLAG' > /tmp/secret_flag.txt && chmod 644 /tmp/secret_flag.txt"

# Verify the flag was created
if docker exec "$STRUTS2_CONTAINER" test -f /tmp/secret_flag.txt; then
  echo "Flag file created successfully at /tmp/secret_flag.txt" >&2
else
  echo "Error: Failed to create flag file" >&2
  exit 1
fi

exit 0
