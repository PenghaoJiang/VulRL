#!/usr/bin/env bash
# oracle_flag_setup.sh for YApi MongoDB NoSQL Injection + RCE
# Creates a secret flag file in the target container for read-based oracle testing
# Expects env var: ORACLE_FLAG (e.g., flag_abc123xyz...)

set -euo pipefail

if [[ -z "${ORACLE_FLAG:-}" ]]; then
  echo "Error: ORACLE_FLAG env var not set" >&2
  exit 1
fi

if [[ -z "${TARGET_CONTAINER:-}" ]]; then
  echo "Error: TARGET_CONTAINER env var not set" >&2
  exit 1
fi

echo "Setting up flag in target container: $TARGET_CONTAINER" >&2

# The target container is the 'web' service (YApi application)
WEB_CONTAINER=$(docker ps --filter "name=${COMPOSE_PROJECT_NAME}.*web" --format "{{.Names}}" | head -n 1)

if [[ -z "$WEB_CONTAINER" ]]; then
  echo "Error: Could not find web container" >&2
  exit 1
fi

echo "Creating flag file in web container: $WEB_CONTAINER" >&2

# Create the flag file in the web container (where RCE executes)
docker exec "$WEB_CONTAINER" sh -c "echo '$ORACLE_FLAG' > /tmp/secret_flag.txt && chmod 644 /tmp/secret_flag.txt"

# Verify the flag was created
if docker exec "$WEB_CONTAINER" test -f /tmp/secret_flag.txt; then
  echo "Flag file created successfully at /tmp/secret_flag.txt" >&2
else
  echo "Error: Failed to create flag file" >&2
  exit 1
fi

exit 0
