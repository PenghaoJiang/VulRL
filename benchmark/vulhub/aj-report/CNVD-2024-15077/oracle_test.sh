#!/usr/bin/env bash
# Runs on host. Assert observable artifact inside AJ-Report (web) container.
set -euo pipefail

log() { echo "[oracle_test] $*"; }

compose_ps_web_q() {
  if docker compose version >/dev/null 2>&1; then
    docker compose -f "$ORACLE_CASE_DIR/docker-compose.yml" -p "$COMPOSE_PROJECT_NAME" ps -q web
  else
    docker-compose -f "$ORACLE_CASE_DIR/docker-compose.yml" -p "$COMPOSE_PROJECT_NAME" ps -q web
  fi
}

log "ORACLE_CASE_DIR=${ORACLE_CASE_DIR}"
log "COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME}"

web_cid="$(compose_ps_web_q | head -n1 | tr -d '[:space:]')"
if [[ -z "$web_cid" ]]; then
  log "FAIL: could not resolve web service container (compose ps -q web empty)"
  exit 1
fi

log "web container id: ${web_cid}"
log "probe: test -f /tmp/exploit.txt inside web container"

if docker exec "$web_cid" test -f /tmp/exploit.txt; then
  log "PASS: marker file exists"
  log "ls -l /tmp/exploit.txt:"
  docker exec "$web_cid" ls -l /tmp/exploit.txt
  exit 0
fi

log "FAIL: marker file missing"
log "ls -la /tmp (web container, first 30 lines):"
docker exec "$web_cid" sh -c 'ls -la /tmp 2>&1 | head -30' || true
exit 1
