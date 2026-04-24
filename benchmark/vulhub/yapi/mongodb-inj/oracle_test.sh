#!/usr/bin/env bash
# oracle_test.sh for YApi MongoDB NoSQL Injection + RCE (read-based oracle)
# Checks if oracle_solution.sh successfully extracted the flag
# 
# Args:
#   $1 = stdout from oracle_solution.sh
#   $2 = expected flag value (ORACLE_FLAG)
#
# Returns:
#   0 = flag successfully extracted (found in stdout)
#   1 = flag not extracted (not found in stdout)

set -euo pipefail

SOLUTION_OUTPUT="${1:-}"
EXPECTED_FLAG="${2:-}"

if [[ -z "$EXPECTED_FLAG" ]]; then
  echo "Error: expected flag (arg 2) not provided" >&2
  exit 2
fi

if [[ -z "$SOLUTION_OUTPUT" ]]; then
  echo "Error: solution output (arg 1) is empty" >&2
  exit 1
fi

# Check if the expected flag appears in the solution output
if echo "$SOLUTION_OUTPUT" | grep -qF "$EXPECTED_FLAG"; then
  echo "Success: Flag found in solution output" >&2
  exit 0
else
  echo "Failure: Flag not found in solution output" >&2
  echo "Expected: $EXPECTED_FLAG" >&2
  echo "Got: ${SOLUTION_OUTPUT:0:200}" >&2
  exit 1
fi
