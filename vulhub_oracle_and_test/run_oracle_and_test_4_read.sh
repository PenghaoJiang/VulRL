#!/usr/bin/env bash
# Standalone Vulhub oracle runner for READ-BASED oracles (SQLi, LFI, etc.)
# Mirrors run_oracle_and_test_4_rce.sh structure but:
#   1. Generates a unique flag (flag_<20 random chars>)
#   2. Runs flag_setup.sh to insert the flag into the target
#   3. Captures oracle_solution.sh stdout
#   4. Passes both stdout and flag to oracle_test.sh for verification
#
# Usage:
#   bash ./run_oracle_and_test_4_read.sh /data1/jph/VulRL/benchmark/vulhub/django/CVE-2022-34265
#
# Expects in the case directory:
#   - oracle_flag_setup.sh — runs on the *host* to insert flag into target (expects ORACLE_FLAG env var)
#   - oracle_solution.sh   — executed *inside* the attacker via docker exec (extracts flag to stdout)
#   - oracle_test.sh       — runs on the *host* with $1=stdout, $2=expected_flag (exit 0/1)
#
# Env passed into the attacker for oracle_solution.sh (docker exec -e):
#   TARGET_CONTAINER, TARGET_CONTAINER_ID, COMPOSE_PROJECT_NAME, ATTACKER_CONTAINER, ORACLE_FLAG
#
# Env exported on the host for oracle_flag_setup.sh and oracle_test.sh:
#   TARGET_CONTAINER, TARGET_CONTAINER_ID, COMPOSE_PROJECT_NAME, ATTACKER_CONTAINER,
#   ORACLE_CASE_DIR (absolute path to the case directory), ORACLE_FLAG
#
# oracle_test.sh receives:
#   $1 = stdout from oracle_solution.sh
#   $2 = expected flag value (ORACLE_FLAG)
#
# Optional env:
#   KEEP_RUNNING=1     Do not tear down compose/attacker on exit (for debugging)
#   STARTUP_SLEEP=8    Seconds to wait after compose up (default 8)

set -euo pipefail

usage() {
  echo "Usage: $0 <vulhub_case_dir>" >&2
  echo "  Example: $0 /data1/jph/VulRL/benchmark/vulhub/django/CVE-2022-34265" >&2
  exit 2
}

if [[ "${1:-}" == "" || "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
fi

VULHUB_CASE_DIR="$(readlink -f "$1")"
if [[ ! -d "$VULHUB_CASE_DIR" ]]; then
  echo "Error: not a directory: $1" >&2
  exit 2
fi
if [[ ! -f "$VULHUB_CASE_DIR/docker-compose.yml" && ! -f "$VULHUB_CASE_DIR/docker-compose.yaml" ]]; then
  echo "Error: no docker-compose.yml(.yaml) under $VULHUB_CASE_DIR" >&2
  exit 2
fi
if [[ ! -f "$VULHUB_CASE_DIR/oracle_flag_setup.sh" ]]; then
  echo "Error: missing $VULHUB_CASE_DIR/oracle_flag_setup.sh" >&2
  exit 2
fi
if [[ ! -f "$VULHUB_CASE_DIR/oracle_solution.sh" ]]; then
  echo "Error: missing $VULHUB_CASE_DIR/oracle_solution.sh" >&2
  exit 2
fi
if [[ ! -f "$VULHUB_CASE_DIR/oracle_test.sh" ]]; then
  echo "Error: missing $VULHUB_CASE_DIR/oracle_test.sh" >&2
  exit 2
fi

STARTUP_SLEEP="${STARTUP_SLEEP:-8}"
KEEP_RUNNING="${KEEP_RUNNING:-0}"

# --- Generate unique flag ---
ORACLE_FLAG="flag_$(head /dev/urandom | tr -dc a-z0-9 | head -c 20)"
echo "[run_oracle_and_test] Generated flag: $ORACLE_FLAG"

# --- match vulhub_adapter._detect_compose_command ---
detect_compose_cmd() {
  if docker compose version >/dev/null 2>&1; then
    echo "docker compose"
  elif docker-compose version >/dev/null 2>&1; then
    echo "docker-compose"
  else
    echo "docker compose"
  fi
}

COMPOSE_CMD_STR="$(detect_compose_cmd)"
compose() {
  # shellcheck disable=SC2086
  $COMPOSE_CMD_STR -p "$COMPOSE_PROJECT_NAME" "$@"
}

# Project name: lowercase alnum + underscore + 8 hex
case_slug="$(basename "$VULHUB_CASE_DIR" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_]/_/g')"
COMPOSE_PROJECT_NAME="vulhub_${case_slug}_$(openssl rand -hex 4)"
ATTACKER_NAME="attacker_${COMPOSE_PROJECT_NAME}"

cleanup_on_exit() {
  if [[ "$KEEP_RUNNING" == "1" ]]; then
    echo "[run_oracle_and_test] KEEP_RUNNING=1 — leaving project=$COMPOSE_PROJECT_NAME attacker=$ATTACKER_NAME"
  else
    docker rm -f "$ATTACKER_NAME" >/dev/null 2>&1 || true
    if [[ -d "$VULHUB_CASE_DIR" ]]; then
      (cd "$VULHUB_CASE_DIR" && compose down -v >/dev/null 2>&1) || true
    fi
  fi
}

trap cleanup_on_exit EXIT

# --- optional stale fixed-name containers ---
for stale in aiohttp nacos-standalone-mysql mysql; do
  if docker rm -f "$stale" >/dev/null 2>&1; then
    echo "[run_oracle_and_test] removed stale container: $stale"
  fi
done

echo "[run_oracle_and_test] compose project: $COMPOSE_PROJECT_NAME"
echo "[run_oracle_and_test] case dir: $VULHUB_CASE_DIR"

(cd "$VULHUB_CASE_DIR" && compose up -d)

echo "[run_oracle_and_test] waiting ${STARTUP_SLEEP}s for services..."
sleep "$STARTUP_SLEEP"

# First container id from compose ps -q
mapfile -t CIDS < <(cd "$VULHUB_CASE_DIR" && compose ps -q | sed '/^$/d')
if [[ ${#CIDS[@]} -eq 0 ]]; then
  echo "Error: no containers reported by compose ps -q" >&2
  exit 1
fi
TARGET_CID="${CIDS[0]}"
TARGET_NAME="$(docker inspect -f '{{.Name}}' "$TARGET_CID" | sed 's|^/||')"

# First network name on that container
mapfile -t NETS < <(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{printf "%s\n" $k}}{{end}}' "$TARGET_CID" | sed '/^$/d')
if [[ ${#NETS[@]} -eq 0 ]]; then
  echo "Error: target container has no attached networks" >&2
  exit 1
fi
NETWORK_NAME="${NETS[0]}"

echo "[run_oracle_and_test] target container: $TARGET_NAME ($TARGET_CID)"
echo "[run_oracle_and_test] compose network: $NETWORK_NAME"

# --- cve-attacker image ---
if ! docker image inspect cve-attacker:latest >/dev/null 2>&1; then
  echo "[run_oracle_and_test] building cve-attacker:latest ..."
  tmpdf="$(mktemp -d)"
  cat >"$tmpdf/Dockerfile" <<'DOCKERFILE'
FROM python:3.11-slim
RUN apt-get update && apt-get install -y curl wget netcat-traditional nmap dnsutils iputils-ping nikto && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir requests sqlmap
WORKDIR /attacker
CMD ["tail", "-f", "/dev/null"]
DOCKERFILE
  docker build -t cve-attacker:latest "$tmpdf"
  rm -rf "$tmpdf"
fi

# --- attacker on same network as target ---
docker run -d --rm \
  --name "$ATTACKER_NAME" \
  --network "$NETWORK_NAME" \
  cve-attacker:latest \
  tail -f /dev/null

echo "[run_oracle_and_test] attacker: $ATTACKER_NAME"

docker_exec_attacker_env=(
  -e "TARGET_CONTAINER=$TARGET_NAME"
  -e "TARGET_CONTAINER_ID=$TARGET_CID"
  -e "COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME"
  -e "ATTACKER_CONTAINER=$ATTACKER_NAME"
  -e "ORACLE_FLAG=$ORACLE_FLAG"
)

run_host_script_with_env() {
  local script_name="$1"
  (
    export TARGET_CONTAINER="$TARGET_NAME"
    export TARGET_CONTAINER_ID="$TARGET_CID"
    export COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT_NAME"
    export ATTACKER_CONTAINER="$ATTACKER_NAME"
    export ORACLE_CASE_DIR="$VULHUB_CASE_DIR"
    export ORACLE_FLAG="$ORACLE_FLAG"
    cd "$VULHUB_CASE_DIR"
    bash "./$script_name"
  )
}

validate_oracle_test_rc() {
  local phase="$1" rc="$2"
  if [[ "$rc" != "0" && "$rc" != "1" ]]; then
    echo "Error: ${phase}: oracle_test.sh must exit 0 or 1, got $rc" >&2
    exit "$rc"
  fi
}

echo "[run_oracle_and_test] running oracle_flag_setup.sh (insert flag into target) ..."
run_host_script_with_env "oracle_flag_setup.sh"

echo "[run_oracle_and_test] oracle_test.sh #1 (before solution; expect exit 1 = flag not yet extracted) ..."
set +e
(
  export TARGET_CONTAINER="$TARGET_NAME"
  export TARGET_CONTAINER_ID="$TARGET_CID"
  export COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT_NAME"
  export ATTACKER_CONTAINER="$ATTACKER_NAME"
  export ORACLE_CASE_DIR="$VULHUB_CASE_DIR"
  export ORACLE_FLAG="$ORACLE_FLAG"
  cd "$VULHUB_CASE_DIR"
  bash ./oracle_test.sh "" "$ORACLE_FLAG"
)
pre_rc=$?
set -e
validate_oracle_test_rc "pre-solution" "$pre_rc"
if [[ "$pre_rc" != "1" ]]; then
  echo "Error: pre-solution oracle_test.sh expected exit 1 (not observable), got $pre_rc" >&2
  echo "  (Often: flag already extracted — dirty state — or oracle_test is too weak.)" >&2
  exit 2
fi

echo "[run_oracle_and_test] running oracle_solution.sh (host file → docker exec -i attacker bash -s) ..."
SOLUTION_OUTPUT=$(docker exec -i "${docker_exec_attacker_env[@]}" "$ATTACKER_NAME" bash -s \
  -- <"$VULHUB_CASE_DIR/oracle_solution.sh")

echo "[run_oracle_and_test] oracle_solution.sh output:"
echo "$SOLUTION_OUTPUT"

echo "[run_oracle_and_test] oracle_test.sh #2 (after solution; expect exit 0 = flag extracted) ..."
set +e
(
  export TARGET_CONTAINER="$TARGET_NAME"
  export TARGET_CONTAINER_ID="$TARGET_CID"
  export COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT_NAME"
  export ATTACKER_CONTAINER="$ATTACKER_NAME"
  export ORACLE_CASE_DIR="$VULHUB_CASE_DIR"
  export ORACLE_FLAG="$ORACLE_FLAG"
  cd "$VULHUB_CASE_DIR"
  bash ./oracle_test.sh "$SOLUTION_OUTPUT" "$ORACLE_FLAG"
)
post_rc=$?
set -e
validate_oracle_test_rc "post-solution" "$post_rc"

echo "[run_oracle_and_test] ORACLE_TEST_PRE=${pre_rc} ORACLE_TEST_POST=${post_rc}"

exit "$post_rc"
