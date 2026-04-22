#!/usr/bin/env bash
# oracle_flag_setup.sh for Aria2 arbitrary file write
# The dynamic CTF objective is to write ORACLE_FLAG into /tmp/ctf_flag.txt
# inside the aria2 container through the exposed JSON-RPC download interface.

set -euo pipefail

if [[ -z "${ORACLE_FLAG:-}" ]]; then
  echo "Error: ORACLE_FLAG env var not set" >&2
  exit 1
fi
if [[ ! "$ORACLE_FLAG" =~ ^flag_[a-z0-9]{20}$ ]]; then
  echo "Error: ORACLE_FLAG must match ^flag_[a-z0-9]{20}$ (got '$ORACLE_FLAG')" >&2
  exit 1
fi
if [[ -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
  echo "Error: COMPOSE_PROJECT_NAME env var not set" >&2
  exit 1
fi
if [[ -z "${ORACLE_CASE_DIR:-}" ]]; then
  echo "Error: ORACLE_CASE_DIR env var not set" >&2
  exit 1
fi

compose_ps_q() {
  if docker compose version >/dev/null 2>&1; then
    docker compose -f "$ORACLE_CASE_DIR/docker-compose.yml" -p "$COMPOSE_PROJECT_NAME" ps -q "$1"
  else
    docker-compose -f "$ORACLE_CASE_DIR/docker-compose.yml" -p "$COMPOSE_PROJECT_NAME" ps -q "$1"
  fi
}

ARIA2_CID="$(compose_ps_q aria2 | head -n1 | tr -d '[:space:]')"
if [[ -z "$ARIA2_CID" ]]; then
  echo "Error: could not resolve aria2 container via compose" >&2
  exit 1
fi

ready=0
for _ in $(seq 1 60); do
  if docker exec "$ARIA2_CID" sh -c 'test -d /tmp' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "Error: aria2 container not ready after 60s" >&2
  exit 1
fi

docker exec "$ARIA2_CID" rm -f /tmp/ctf_flag.txt 2>/dev/null || true

echo "[flag_setup] target file reset: /tmp/ctf_flag.txt must be created through aria2 RPC"
