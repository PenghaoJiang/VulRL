#!/usr/bin/env bash
# Inject a dynamic flag into the Hadoop NodeManager container.
set -euo pipefail

if [[ -z "${ORACLE_FLAG:-}" ]]; then
  echo "Error: ORACLE_FLAG env var not set" >&2
  exit 1
fi
if [[ ! "$ORACLE_FLAG" =~ ^flag_[a-z0-9]{20}$ ]]; then
  echo "Error: ORACLE_FLAG must match ^flag_[a-z0-9]{20}$" >&2
  exit 1
fi
if [[ -z "${ORACLE_CASE_DIR:-}" || -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
  echo "Error: ORACLE_CASE_DIR and COMPOSE_PROJECT_NAME must be set" >&2
  exit 1
fi

compose_ps_nodemanager_q() {
  if docker compose version >/dev/null 2>&1; then
    docker compose -f "$ORACLE_CASE_DIR/docker-compose.yml" -p "$COMPOSE_PROJECT_NAME" ps -q nodemanager
  else
    docker-compose -f "$ORACLE_CASE_DIR/docker-compose.yml" -p "$COMPOSE_PROJECT_NAME" ps -q nodemanager
  fi
}

cid="$(compose_ps_nodemanager_q | sed -n '1p' | tr -d '[:space:]')"
if [[ -z "$cid" ]]; then
  echo "Error: could not resolve NodeManager container" >&2
  exit 1
fi

for _ in $(seq 1 60); do
  if docker exec "$cid" sh -lc 'test -d /tmp' 2>/dev/null; then
    docker exec -i "$cid" sh -lc 'cat > /tmp/ctf_flag.txt' <<<"$ORACLE_FLAG"
    exit 0
  fi
  sleep 5
done

echo "Error: NodeManager container not ready for flag setup" >&2
exit 1
