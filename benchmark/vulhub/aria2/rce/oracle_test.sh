#!/usr/bin/env bash
# oracle_test.sh for Aria2 arbitrary file write
#   0 = /tmp/ctf_flag.txt exists in target and contains expected flag
#   1 = expected file/content not observed
#   2 = harness misuse

set -euo pipefail

EXPECTED_FLAG="${2:-${ORACLE_FLAG:-}}"

if [[ -z "$EXPECTED_FLAG" ]]; then
  echo "Error: expected flag not provided as arg 2 or ORACLE_FLAG" >&2
  exit 2
fi
if [[ ! "$EXPECTED_FLAG" =~ ^flag_[a-z0-9]{20}$ ]]; then
  echo "Error: expected flag must match ^flag_[a-z0-9]{20}$" >&2
  exit 2
fi
if [[ -z "${ORACLE_CASE_DIR:-}" || -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
  echo "Error: ORACLE_CASE_DIR and COMPOSE_PROJECT_NAME must be set" >&2
  exit 2
fi

cd "$ORACLE_CASE_DIR"
compose() {
  docker compose -p "$COMPOSE_PROJECT_NAME" "$@"
}

aria2_cid="$(compose ps -q aria2 | head -n1 | tr -d '[:space:]')"
[[ -n "$aria2_cid" ]] || { echo "[oracle_test] ERROR: aria2 container not found" >&2; exit 2; }

if ! docker exec "$aria2_cid" test -f /tmp/ctf_flag.txt 2>/dev/null; then
  echo "[oracle_test] FAIL: /tmp/ctf_flag.txt missing"
  exit 1
fi

observed="$(docker exec "$aria2_cid" sh -c 'cat /tmp/ctf_flag.txt' 2>/dev/null | tr -d '\r\n')"
if [[ "$observed" == "$EXPECTED_FLAG" ]]; then
  echo "[oracle_test] SUCCESS: target file contains expected flag"
  exit 0
fi

echo "[oracle_test] FAIL: target file content mismatch"
echo "[oracle_test] Expected: $EXPECTED_FLAG"
echo "[oracle_test] Observed: ${observed:0:200}"
exit 1
