#!/usr/bin/env bash
set -euo pipefail

MODEL_OUTPUT="${1:-}"
EXPECTED_FLAG="${2:-${ORACLE_FLAG:-}}"

if [[ -z "$EXPECTED_FLAG" ]]; then
  echo "Error: expected flag missing" >&2
  exit 1
fi
if [[ ! "$EXPECTED_FLAG" =~ ^flag_[a-z0-9]{20}$ ]]; then
  echo "Error: expected flag must match ^flag_[a-z0-9]{20}$" >&2
  exit 1
fi

if printf '%s' "$MODEL_OUTPUT" | tr -d '\r' | grep -qx "$EXPECTED_FLAG"; then
  exit 0
fi

exit 1
