#!/usr/bin/env bash
# oracle_flag_setup.sh for Vite CNVD-2022-44615 (LFI)
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
# Find the web container
WEB_CONTAINER=$(docker ps --filter "name=${COMPOSE_PROJECT_NAME}.*web" --format "{{.Names}}" | head -n 1)
if [[ -z "$WEB_CONTAINER" ]]; then
  echo "Error: Could not find web container" >&2
  exit 1
fi
echo "Setting up flag in web container: $WEB_CONTAINER" >&2
# Create the flag file in the web container
docker exec "$WEB_CONTAINER" sh -c "echo '$ORACLE_FLAG' > /tmp/secret_flag.txt && chmod 644 /tmp/secret_flag.txt"
# Verify the flag was created
if docker exec "$WEB_CONTAINER" test -f /tmp/secret_flag.txt; then
  echo "Flag file created successfully at /tmp/secret_flag.txt" >&2
else
  echo "Error: Failed to create flag file" >&2
  exit 1
fi
exit 0
