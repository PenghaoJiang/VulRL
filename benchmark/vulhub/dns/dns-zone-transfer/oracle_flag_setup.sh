#!/usr/bin/env bash
# oracle_flag_setup.sh for DNS Zone Transfer (AXFR) misconfiguration
# Plants a TXT record containing $ORACLE_FLAG under a randomly-chosen label inside the
# vulhub.org zone served by Bind9. The label is unguessable per-run, so the only
# reliable way to learn it and read the flag is to perform an AXFR zone transfer --
# which this environment (mis)permits. Expects env vars: ORACLE_FLAG,
# COMPOSE_PROJECT_NAME, ORACLE_CASE_DIR.

set -euo pipefail

if [[ -z "${ORACLE_FLAG:-}" ]]; then
  echo "Error: ORACLE_FLAG env var not set" >&2
  exit 1
fi
if [[ ! "$ORACLE_FLAG" =~ ^flag_[a-z0-9]{20}$ ]]; then
  echo "Error: ORACLE_FLAG does not match ^flag_[a-z0-9]{20}\$ (got: ${ORACLE_FLAG})" >&2
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

CID="$(compose_ps_q dns | head -n1 | tr -d '[:space:]')"
if [[ -z "$CID" ]]; then
  echo "Error: could not resolve dns container via compose" >&2
  exit 1
fi
echo "[flag_setup] dns container id: $CID"

# Wait for Bind and the zone file to be in place.
ready=0
for _ in $(seq 1 60); do
  if docker exec "$CID" rndc status >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "Error: Bind9 not responding to rndc after 60s" >&2
  exit 1
fi

# Random label, so the record is only discoverable through AXFR (not via a guessable
# direct query). Use `od` (bounded read) to avoid the tr-from-urandom | head SIGPIPE
# that would otherwise kill the script under `set -o pipefail`.
LABEL="x$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')"

# Rewrite the zone file via a staging file (sed -i fails on bind-mounted files from
# macOS Docker). Strip any previous `x*` flag label so re-runs are idempotent, ensure
# a trailing newline, then append the TXT record. Finally rndc reload.
docker exec -e "LABEL=$LABEL" -e "FLAG=$ORACLE_FLAG" "$CID" sh -c '
set -e
ZONE=/etc/bind/vulhub.db
TMP=/tmp/zone.new
awk "/^x[0-9a-z]+ IN TXT .flag_/ {next} {print}" "$ZONE" > "$TMP"
# Ensure trailing newline.
tail -c1 "$TMP" | od -An -c | grep -q "\\\\n" || printf "\n" >> "$TMP"
printf "%s IN TXT \"%s\"\n" "$LABEL" "$FLAG" >> "$TMP"
cat "$TMP" > "$ZONE"
rndc reload >/dev/null
'

# Verify the record is live by doing an AXFR ourselves (from inside the dns container
# where AXFR is implicitly permitted from localhost).
sleep 1
OBSERVED="$(docker exec "$CID" dig @127.0.0.1 vulhub.org AXFR +tcp +short 2>/dev/null || true)"
if ! grep -qF "$ORACLE_FLAG" <<<"$OBSERVED"; then
  echo "Error: planted flag not present in AXFR output" >&2
  echo "observed: $OBSERVED" >&2
  exit 1
fi

echo "[flag_setup] flag planted at <random-label>.vulhub.org TXT inside the zone; reachable only via AXFR"
