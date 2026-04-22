#!/usr/bin/env bash
# oracle_flag_setup.sh for ThinkPHP 5.0.23 RCE
# Plants a secret flag file in the web container at a path not served by the web root.
# The flag is only reachable by exploiting the Request::__construct() filter injection
# (POST /index.php?s=captcha with _method=__construct&filter[]=system&...) to run a
# shell command. Expects env vars: ORACLE_FLAG, COMPOSE_PROJECT_NAME, ORACLE_CASE_DIR.

set -euo pipefail

if [[ -z "${ORACLE_FLAG:-}" ]]; then
  echo "Error: ORACLE_FLAG env var not set" >&2
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

WEB_CID="$(compose_ps_q web | head -n1 | tr -d '[:space:]')"
if [[ -z "$WEB_CID" ]]; then
  echo "Error: could not resolve web container via compose" >&2
  exit 1
fi

echo "[flag_setup] web container id: $WEB_CID"

# Wait for /tmp to be accessible in the container
ready=0
for _ in $(seq 1 60); do
  if docker exec "$WEB_CID" sh -c 'test -d /tmp' >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "Error: /tmp not accessible in web container after 60s" >&2
  exit 1
fi

# Plant the flag via env-var pass-through so it doesn't appear on the command line.
# Keep readable by www-data (the PHP worker uid=33) — rely on default world-readable umask,
# then chmod 0644 to be explicit.
docker exec -e "F=$ORACLE_FLAG" "$WEB_CID" sh -c 'printf %s "$F" > /tmp/secret_flag.txt && chmod 0644 /tmp/secret_flag.txt'

OBSERVED="$(docker exec "$WEB_CID" cat /tmp/secret_flag.txt)"
if [[ "$OBSERVED" != "$ORACLE_FLAG" ]]; then
  echo "Error: flag verification failed (planted value does not match)" >&2
  exit 1
fi

echo "[flag_setup] flag planted at /tmp/secret_flag.txt in web container (not served by web root; reachable only via RCE)"
