#!/usr/bin/env bash
set -euo pipefail
actual="$(printf '%s' "${1:-}" | tr -d '\r' | sed -n '1p')"
expected="${2:-${ORACLE_FLAG:-}}"
[[ -n "$expected" ]] || exit 2
[[ "$actual" == "$expected" ]]
