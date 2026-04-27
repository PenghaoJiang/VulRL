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
if [[ -z "${TARGET_CONTAINER:-}" ]]; then
  echo "Error: TARGET_CONTAINER env var not set" >&2
  exit 1
fi

docker exec "$TARGET_CONTAINER" sh -lc "printf '%s\n' \"$ORACLE_FLAG\" >/tmp/ctf_flag.txt && chmod 644 /tmp/ctf_flag.txt"
