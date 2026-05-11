#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${ORACLE_FLAG:-}" ]]; then
  echo "Error: ORACLE_FLAG env var not set" >&2
  exit 1
fi
if [[ ! "$ORACLE_FLAG" =~ ^flag_[a-z0-9]{20}$ ]]; then
  echo "Error: ORACLE_FLAG must match ^flag_[a-z0-9]{20}$" >&2
  exit 1
fi
if [[ -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
  echo "Error: COMPOSE_PROJECT_NAME env var not set" >&2
  exit 1
fi

WEB_CONTAINER="$(docker ps -q \
  --filter "label=com.docker.compose.project=${COMPOSE_PROJECT_NAME}" \
  --filter "label=com.docker.compose.service=web" | head -n 1)"

if [[ -z "$WEB_CONTAINER" ]]; then
  echo "Error: could not locate YApi web container for project ${COMPOSE_PROJECT_NAME}" >&2
  exit 1
fi

docker exec "$WEB_CONTAINER" sh -lc \
  "printf '%s\n' \"$ORACLE_FLAG\" >/tmp/ctf_flag.txt && chmod 644 /tmp/ctf_flag.txt"
