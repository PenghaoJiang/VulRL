#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ORCH_DIR="$REPO_ROOT/worker_orchestrator"
DATASET_DIR="$REPO_ROOT/dataset"
LOG_DIR="$REPO_ROOT/logs/server"

mkdir -p "$LOG_DIR"

RUN_STAMP="${RUN_STAMP:-$(date +%Y%m%d_%H%M%S)}"
LOG_FILE="$LOG_DIR/convert_ctf_${RUN_STAMP}.log"
LATEST_LOG="$LOG_DIR/convert_latest.log"

if [ ! -x "$ORCH_DIR/venv/bin/python" ]; then
  echo "worker_orchestrator venv not found."
  echo "Run: bash $ORCH_DIR/setup.sh"
  exit 1
fi

ln -sfn "$LOG_FILE" "$LATEST_LOG"
exec > >(tee -a "$LOG_FILE") 2>&1

OUTPUT_PATH="${OUTPUT_PATH:-$DATASET_DIR/ctf_parquet/train_ctf_subtask_combined.parquet}"
CTFMIX_ROOT="${CTFMIX_ROOT:-$REPO_ROOT/benchmark/ctfmix}"
NYU_LIST="${NYU_LIST:-}"
NYU_SUBTASK_LIST="${NYU_SUBTASK_LIST:-$DATASET_DIR/ctf_docker_nyu_subtask_cases.txt}"
CYBENCH_LIST="${CYBENCH_LIST:-$DATASET_DIR/ctf_docker_cybench_cases.txt}"
MAX_STEPS="${MAX_STEPS:-30}"
TIMEOUT="${TIMEOUT:-30}"

ARGS=(
  "$REPO_ROOT/dataset/dataset_converter_ctf.py"
  --ctfmix-root "$CTFMIX_ROOT"
  --output "$OUTPUT_PATH"
  --max-steps "$MAX_STEPS"
  --timeout "$TIMEOUT"
)

if [ -n "$NYU_LIST" ]; then
  if [ ! -f "$NYU_LIST" ]; then
    echo "NYU list not found: $NYU_LIST"
    exit 1
  fi
  ARGS+=(--nyu-list "$NYU_LIST")
fi

if [ -n "$NYU_SUBTASK_LIST" ]; then
  if [ ! -f "$NYU_SUBTASK_LIST" ]; then
    echo "NYU subtask list not found: $NYU_SUBTASK_LIST"
    exit 1
  fi
  ARGS+=(--nyu-subtask-list "$NYU_SUBTASK_LIST")
fi

if [ -n "$CYBENCH_LIST" ]; then
  if [ ! -f "$CYBENCH_LIST" ]; then
    echo "Cybench list not found: $CYBENCH_LIST"
    exit 1
  fi
  ARGS+=(--cybench-list "$CYBENCH_LIST")
fi

if [ ${#ARGS[@]} -le 9 ]; then
  echo "No dataset lists were provided."
  echo "Set NYU_LIST and/or NYU_SUBTASK_LIST and/or CYBENCH_LIST."
  exit 1
fi

echo "============================================================"
echo "Convert CTF Training Data"
echo "============================================================"
echo "Repo root: $REPO_ROOT"
echo "CTFMix root: $CTFMIX_ROOT"
echo "Output parquet: $OUTPUT_PATH"
echo "NYU list: ${NYU_LIST:-<disabled>}"
echo "NYU subtask list: ${NYU_SUBTASK_LIST:-<disabled>}"
echo "Cybench list: ${CYBENCH_LIST:-<disabled>}"
echo "Max steps: $MAX_STEPS"
echo "Timeout: $TIMEOUT"
echo "Log file: $LOG_FILE"
echo "============================================================"
echo

"$ORCH_DIR/venv/bin/python" "${ARGS[@]}"

echo
echo "Conversion finished."
echo "Parquet: $OUTPUT_PATH"
echo "Log: $LOG_FILE"
