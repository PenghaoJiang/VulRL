#!/usr/bin/env bash
# Runs on host. Assert observable artifact inside AJ-Report (web) container.
set -euo pipefail

compose_ps_web_q() {
  if docker compose version >/dev/null 2>&1; then
    docker compose -f "$ORACLE_CASE_DIR/docker-compose.yml" -p "$COMPOSE_PROJECT_NAME" ps -q web
  else
    docker-compose -f "$ORACLE_CASE_DIR/docker-compose.yml" -p "$COMPOSE_PROJECT_NAME" ps -q web
  fi
}

web_cid="$(compose_ps_web_q | head -n1 | tr -d '[:space:]')"
if [[ -z "$web_cid" ]]; then
  echo "oracle_test: could not resolve web service container" >&2
  exit 1
fi

if docker exec "$web_cid" test -f /tmp/exploit.txt; then
  exit 0
fi
exit 1
