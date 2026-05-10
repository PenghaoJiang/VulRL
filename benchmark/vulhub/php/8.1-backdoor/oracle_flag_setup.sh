#!/usr/bin/env bash
set -euo pipefail
if [[ -z "${ORACLE_FLAG:-}" ]]; then echo "Error: ORACLE_FLAG env var not set" >&2; exit 1; fi
if [[ ! "$ORACLE_FLAG" =~ ^flag_[a-z0-9]{20}$ ]]; then echo "Error: ORACLE_FLAG must match ^flag_[a-z0-9]{20}$" >&2; exit 1; fi
if [[ -z "${ORACLE_CASE_DIR:-}" || -z "${COMPOSE_PROJECT_NAME:-}" ]]; then echo "Error: ORACLE_CASE_DIR and COMPOSE_PROJECT_NAME must be set" >&2; exit 1; fi
if docker compose version >/dev/null 2>&1; then
  cid="$(docker compose -f "$ORACLE_CASE_DIR/docker-compose.yml" -p "$COMPOSE_PROJECT_NAME" ps -q web | sed -n '1p' | tr -d '[:space:]')"
else
  cid="$(docker-compose -f "$ORACLE_CASE_DIR/docker-compose.yml" -p "$COMPOSE_PROJECT_NAME" ps -q web | sed -n '1p' | tr -d '[:space:]')"
fi
[[ -n "$cid" ]] || { echo "Error: could not resolve PHP web container" >&2; exit 1; }
docker exec -i "$cid" sh -lc 'cat > /tmp/ctf_flag.txt' <<<"$ORACLE_FLAG"
