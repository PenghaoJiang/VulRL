#!/usr/bin/env bash
# Standalone Vulhub oracle runner: mirrors worker_unit/adapters/vulhub_adapter.py
# for compose bring-up, network attachment, and cve-attacker sidecar.
#
# Usage:
#   bash ./run_oracle_and_test.sh /data1/jph/VulRL/benchmark/vulhub/aj-report/CNVD-2024-15077
#
# Expects in the case directory:
#   - oracle_solution.sh   — file is read on the host; execution is *inside* the attacker
#     via `docker exec -i … bash -s < oracle_solution.sh` (same tools/network as attacker).
#   - oracle_test.sh       — runs on the *host*; use `docker exec "$TARGET_CONTAINER" …`
#     to assert state inside the vulhub target (exit 0 = observable, exit 1 = not).
#
# Env passed into the attacker for oracle_solution.sh (docker exec -e):
#   TARGET_CONTAINER, TARGET_CONTAINER_ID, COMPOSE_PROJECT_NAME, ATTACKER_CONTAINER
#
# Env exported on the host for oracle_test.sh:
#   TARGET_CONTAINER, TARGET_CONTAINER_ID, COMPOSE_PROJECT_NAME, ATTACKER_CONTAINER,
#   ORACLE_CASE_DIR (absolute path to the case directory)
#
# Optional env:
#   KEEP_RUNNING=1     Do not tear down compose/attacker on exit (for debugging)
#   STARTUP_SLEEP=8    Seconds to wait after compose up (default 8, same as adapter)

set -euo pipefail

usage() {
  echo "Usage: $0 <vulhub_case_dir>" >&2
  echo "  Example: $0 /data1/jph/VulRL/benchmark/vulhub/aj-report/CNVD-2024-15077" >&2
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

# Project name: lowercase alnum + underscore + 8 hex (same spirit as adapter)
case_slug="$(basename "$VULHUB_CASE_DIR" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9_]/_/g')"
COMPOSE_PROJECT_NAME="vulhub_${case_slug}_$(openssl rand -hex 4)"
ATTACKER_NAME="attacker_${COMPOSE_PROJECT_NAME}"

cleanup_on_exit() {
  # Do not call exit here: bash preserves the script's pending exit status
  # after the EXIT trap returns (including explicit exit N).
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

# --- optional stale fixed-name containers (vulhub_adapter._cleanup_stale_containers) ---
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

# First container id from compose ps -q (same as adapter: first line)
mapfile -t CIDS < <(cd "$VULHUB_CASE_DIR" && compose ps -q | sed '/^$/d')
if [[ ${#CIDS[@]} -eq 0 ]]; then
  echo "Error: no containers reported by compose ps -q" >&2
  exit 1
fi
TARGET_CID="${CIDS[0]}"
TARGET_NAME="$(docker inspect -f '{{.Name}}' "$TARGET_CID" | sed 's|^/||')"

# First network name on that container (adapter uses networks[0])
mapfile -t NETS < <(docker inspect -f '{{range $k, $v := .NetworkSettings.Networks}}{{printf "%s\n" $k}}{{end}}' "$TARGET_CID" | sed '/^$/d')
if [[ ${#NETS[@]} -eq 0 ]]; then
  echo "Error: target container has no attached networks" >&2
  exit 1
fi
NETWORK_NAME="${NETS[0]}"

echo "[run_oracle_and_test] target container: $TARGET_NAME ($TARGET_CID)"
echo "[run_oracle_and_test] compose network: $NETWORK_NAME"

# --- cve-attacker image (vulhub_adapter._build_attacker_image) ---
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

# --- attacker on same network as target (no bind mount; solution script streamed from host) ---
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
)

echo "[run_oracle_and_test] running oracle_solution.sh (host file → docker exec -i attacker bash -s) ..."
docker exec -i "${docker_exec_attacker_env[@]}" "$ATTACKER_NAME" bash -s \
  -- <"$VULHUB_CASE_DIR/oracle_solution.sh"

echo "[run_oracle_and_test] running oracle_test.sh on host (use docker exec \"\$TARGET_CONTAINER\" …) ..."
set +e
(
  export TARGET_CONTAINER="$TARGET_NAME"
  export TARGET_CONTAINER_ID="$TARGET_CID"
  export COMPOSE_PROJECT_NAME="$COMPOSE_PROJECT_NAME"
  export ATTACKER_CONTAINER="$ATTACKER_NAME"
  export ORACLE_CASE_DIR="$VULHUB_CASE_DIR"
  cd "$VULHUB_CASE_DIR"
  bash ./oracle_test.sh
)
test_rc=$?
set -e

if [[ "$test_rc" != "0" && "$test_rc" != "1" ]]; then
  echo "Error: oracle_test.sh must exit 0 or 1, got $test_rc" >&2
  exit "$test_rc"
fi

echo "[run_oracle_and_test] ORACLE_TEST_RESULT=$test_rc"

exit "$test_rc"
