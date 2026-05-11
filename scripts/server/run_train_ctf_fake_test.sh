#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ORCH_DIR="$REPO_ROOT/worker_orchestrator"
DATASET_DIR="$REPO_ROOT/dataset"
LOG_DIR="$REPO_ROOT/logs/server"

mkdir -p "$LOG_DIR" "$DATASET_DIR/ctf_parquet"

RUN_NAME="${RUN_NAME:-ctf_fake_train_$(date +%Y%m%d_%H%M%S)}"
CHALLENGE_REL_PATH="${CHALLENGE_REL_PATH:-cybench/HKC/web/22-back-to-the-past}"
FAKE_TEST_PARQUET="${FAKE_TEST_PARQUET:-$DATASET_DIR/ctf_parquet/train_ctf_fake_test.parquet}"
MAX_STEPS="${MAX_STEPS:-40}"
TIMEOUT="${TIMEOUT:-30}"
CONVERT_LOG="$LOG_DIR/convert_fake_train_${RUN_NAME}.log"

if [ ! -x "$ORCH_DIR/venv/bin/python" ]; then
  echo "worker_orchestrator venv not found."
  echo "Run: bash $ORCH_DIR/setup.sh"
  exit 1
fi

echo "============================================================"
echo "Build fake-train parquet"
echo "============================================================"
echo "Challenge: $CHALLENGE_REL_PATH"
echo "Output parquet: $FAKE_TEST_PARQUET"
echo "Max steps: $MAX_STEPS"
echo "Timeout: $TIMEOUT"
echo "Convert log: $CONVERT_LOG"
echo "============================================================"
echo

"$ORCH_DIR/venv/bin/python" "$DATASET_DIR/dataset_converter_ctf_fake_test.py" \
  --challenge-rel-path "$CHALLENGE_REL_PATH" \
  --output "$FAKE_TEST_PARQUET" \
  --max-steps "$MAX_STEPS" \
  --timeout "$TIMEOUT" | tee "$CONVERT_LOG"

echo
echo "Launching one-case training smoke run..."
echo

TRAIN_DATA="$FAKE_TEST_PARQUET" \
RUN_NAME="$RUN_NAME" \
EPOCHS="${EPOCHS:-1}" \
TRAIN_BATCH_SIZE="${TRAIN_BATCH_SIZE:-1}" \
POLICY_MINI_BATCH_SIZE="${POLICY_MINI_BATCH_SIZE:-1}" \
MICRO_BATCH_SIZE="${MICRO_BATCH_SIZE:-1}" \
EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-1}" \
N_SAMPLES_PER_PROMPT="${N_SAMPLES_PER_PROMPT:-1}" \
MAX_STEPS="$MAX_STEPS" \
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.5}" \
MAX_MODEL_LEN="${MAX_MODEL_LEN:-32768}" \
PROJECT_NAME="${PROJECT_NAME:-vulrl_ctf_fake_train}" \
bash "$REPO_ROOT/scripts/server/run_ctf_rl_training.sh" "$@"
