#!/usr/bin/env bash
# oracle_flag_setup.sh for XXL-Job Executor Unauthorized Access
# Creates a flag file in the executor container
# Expects env var: ORACLE_FLAG (e.g., flag_abc123xyz...)

set -euo pipefail

# Check if ORACLE_FLAG is set
if [[ -z "${ORACLE_FLAG:-}" ]]; then
    echo "Error: ORACLE_FLAG env var not set" >&2
    exit 1
fi

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Get the compose project name (parent directory name)
PROJECT_NAME=$(basename "$SCRIPT_DIR")

# Find the executor container
EXECUTOR_CONTAINER=$(docker ps --filter "name=${PROJECT_NAME}.*executor" --format "{{.Names}}" | head -n 1)

if [ -z "$EXECUTOR_CONTAINER" ]; then
    echo "Error: Could not find executor container" >&2
    exit 1
fi

echo "Setting up flag in executor container: $EXECUTOR_CONTAINER" >&2

# Create the flag file in the executor container
docker exec "$EXECUTOR_CONTAINER" sh -c "echo '$ORACLE_FLAG' > /tmp/secret_flag.txt && chmod 644 /tmp/secret_flag.txt"

# Verify the flag was created
if docker exec "$EXECUTOR_CONTAINER" test -f /tmp/secret_flag.txt; then
    echo "Flag file created successfully at /tmp/secret_flag.txt" >&2
else
    echo "Error: Failed to create flag file" >&2
    exit 1
fi

exit 0
