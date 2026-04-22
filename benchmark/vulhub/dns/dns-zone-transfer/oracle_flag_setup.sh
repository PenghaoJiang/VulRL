#!/usr/bin/env bash
# oracle_flag_setup.sh for DNS Zone Transfer (AXFR)
# Plants a per-episode flag as a TXT record under a random label in vulhub.org.
# The label is intentionally unguessable, so the reliable way to discover the
# flag is to perform an AXFR zone transfer against the vulnerable DNS server.

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

DNS_CID="$(compose_ps_q dns | head -n1 | tr -d '[:space:]')"
if [[ -z "$DNS_CID" ]]; then
  echo "Error: could not resolve dns container via compose" >&2
  exit 1
fi

echo "[flag_setup] dns container id: $DNS_CID"

ready=0
for _ in $(seq 1 60); do
  if docker exec "$DNS_CID" rndc status >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
if [[ "$ready" -ne 1 ]]; then
  echo "Error: Bind9 not responding to rndc after 60s" >&2
  exit 1
fi

# Random, non-guessable label. Use od rather than tr/head on /dev/urandom so
# pipefail does not turn a normal SIGPIPE into a script failure.
LABEL="x$(od -An -N6 -tx1 /dev/urandom | tr -d ' \n')"

docker exec -e "LABEL=$LABEL" -e "FLAG=$ORACLE_FLAG" "$DNS_CID" sh -c '
set -e
ZONE=/etc/bind/vulhub.db
TMP=/tmp/vulhub.db.new
awk "/^x[0-9a-f]+[[:space:]]+IN[[:space:]]+TXT[[:space:]]+\"flag_[a-z0-9]+\"/ {next} {print}" "$ZONE" > "$TMP"
tail -c1 "$TMP" | od -An -c | grep -q "\\n" || printf "\n" >> "$TMP"
printf "%s IN TXT \"%s\"\n" "$LABEL" "$FLAG" >> "$TMP"
cat "$TMP" > "$ZONE"
rndc reload >/dev/null
'

sleep 1
OBSERVED="$(docker exec "$DNS_CID" dig @127.0.0.1 vulhub.org AXFR +tcp +short 2>/dev/null || true)"
if ! grep -qF "$ORACLE_FLAG" <<<"$OBSERVED"; then
  echo "Error: planted flag not present in AXFR output" >&2
  echo "Observed AXFR output:" >&2
  echo "$OBSERVED" >&2
  exit 1
fi

echo "[flag_setup] flag planted at ${LABEL}.vulhub.org TXT; reachable through AXFR"
