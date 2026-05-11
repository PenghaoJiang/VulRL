#!/usr/bin/env bash
# Deterministically verify that the submitted output is exactly the dynamic flag.
set -euo pipefail

actual="${1:-}"
expected="${2:-${ORACLE_FLAG:-}}"

actual="$(printf '%s' "$actual" | tr -d '\r' | sed -n '1p')"

if [[ -z "$expected" ]]; then
  exit 2
fi

if [[ "$actual" == "$expected" ]]; then
  exit 0
fi

exit 1
