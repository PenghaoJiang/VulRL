#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
ORCH_DIR="$REPO_ROOT/worker_orchestrator"
DATASET_DIR="$REPO_ROOT/dataset"
LOG_DIR="$REPO_ROOT/logs/server"
REPO_VENV_PYTHON="$REPO_ROOT/../../VulRL/venv/bin/python3.12"

mkdir -p "$LOG_DIR" "$DATASET_DIR/ctf_parquet"

RUN_NAME="${RUN_NAME:-ctf_probe_$(date +%Y%m%d_%H%M%S)}"
CHALLENGE_REL_PATH="${CHALLENGE_REL_PATH:-cybench/HKC/web/22-back-to-the-past}"
PROBE_PARQUET="${PROBE_PARQUET:-$DATASET_DIR/ctf_parquet/train_ctf_probe.parquet}"
MAX_STEPS="${MAX_STEPS:-40}"
TIMEOUT="${TIMEOUT:-30}"
TEMPERATURE="${TEMPERATURE:-0.0}"
TRAIN_BATCH_SIZE="${TRAIN_BATCH_SIZE:-1}"
POLICY_MINI_BATCH_SIZE="${POLICY_MINI_BATCH_SIZE:-1}"
MICRO_BATCH_SIZE="${MICRO_BATCH_SIZE:-1}"
EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-1}"
N_SAMPLES_PER_PROMPT="${N_SAMPLES_PER_PROMPT:-1}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.5}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-131072}"
TRAINER_MAX_PROMPT_LENGTH="${TRAINER_MAX_PROMPT_LENGTH:-2048}"
GENERATOR_MAX_INPUT_LENGTH="${GENERATOR_MAX_INPUT_LENGTH:-4096}"
MAX_GENERATE_LENGTH="${MAX_GENERATE_LENGTH:-2048}"
PROJECT_NAME="${PROJECT_NAME:-vulrl_ctf_probe}"
CONVERT_LOG="$LOG_DIR/convert_ctf_probe_${RUN_NAME}.log"
VERIFY_LOG="$LOG_DIR/verify_ctf_probe_${RUN_NAME}.log"

if [ -x "$ORCH_DIR/venv/bin/python" ]; then
  PROBE_PYTHON="$ORCH_DIR/venv/bin/python"
elif [ -x "$ORCH_DIR/venv/bin/python3" ]; then
  PROBE_PYTHON="$ORCH_DIR/venv/bin/python3"
elif [ -x "$REPO_VENV_PYTHON" ]; then
  PROBE_PYTHON="$REPO_VENV_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PROBE_PYTHON="$(command -v python3)"
elif command -v python >/dev/null 2>&1; then
  PROBE_PYTHON="$(command -v python)"
else
  echo "No usable Python interpreter found for dataset conversion."
  echo "Expected one of:"
  echo "  - $ORCH_DIR/venv/bin/python"
  echo "  - $REPO_VENV_PYTHON"
  echo "  - python3/python on PATH"
  exit 1
fi

echo "============================================================"
echo "Build CTF probe parquet"
echo "============================================================"
echo "Challenge: $CHALLENGE_REL_PATH"
echo "Output parquet: $PROBE_PARQUET"
echo "Max steps: $MAX_STEPS"
echo "Timeout: $TIMEOUT"
echo "Temperature: $TEMPERATURE"
echo "Trainer max prompt length: $TRAINER_MAX_PROMPT_LENGTH"
echo "Generator max input length: $GENERATOR_MAX_INPUT_LENGTH"
echo "Max generate length: $MAX_GENERATE_LENGTH"
echo "Convert log: $CONVERT_LOG"
echo "Verify log: $VERIFY_LOG"
echo "============================================================"
echo

"$PROBE_PYTHON" "$DATASET_DIR/dataset_converter_ctf_fake_test.py" \
  --challenge-rel-path "$CHALLENGE_REL_PATH" \
  --output "$PROBE_PARQUET" \
  --max-steps "$MAX_STEPS" \
  --timeout "$TIMEOUT" | tee "$CONVERT_LOG"

echo
echo "Verifying that the generated prompt explicitly contains known checkpoint answers..."
echo

"$PROBE_PYTHON" - <<'PY' "$PROBE_PARQUET" | tee "$VERIFY_LOG"
import json
import sys
from pathlib import Path
import pandas as pd

parquet_path = Path(sys.argv[1])
df = pd.read_parquet(parquet_path)
if len(df) != 1:
    raise SystemExit(f"Expected exactly one row, got {len(df)}")
row = df.iloc[0].to_dict()

prompt_payload = row["prompt"]
if isinstance(prompt_payload, str):
    prompt_payload = json.loads(prompt_payload)
if isinstance(prompt_payload, list):
    prompt_text = str(prompt_payload[-1]["content"])
else:
    prompt_text = str(prompt_payload)

required_markers = [
    "TEST MODE: scripted CTF integration test.",
    "Checkpoint answers to record during this scripted test:",
    "Final flag ->",
    "submit_subtask",
]
missing = [marker for marker in required_markers if marker not in prompt_text]
if missing:
    raise SystemExit(f"Probe prompt is missing required markers: {missing}")

print("Probe parquet verification OK")
print(f"Prompt chars: {len(prompt_text)}")
print("Prompt preview:")
print(prompt_text[:2000])
PY

echo
echo "Launching one-case probe training run..."
echo "This probe intentionally uses dataset_converter_ctf_fake_test.py so the prompt contains known checkpoint answers and the final flag."
echo "If the LLM follows the scripted checklist, the rollout should be able to collect shaped reward deterministically."
echo

TRAIN_DATA="$PROBE_PARQUET" \
RUN_NAME="$RUN_NAME" \
EPOCHS="${EPOCHS:-1}" \
TRAIN_BATCH_SIZE="$TRAIN_BATCH_SIZE" \
POLICY_MINI_BATCH_SIZE="$POLICY_MINI_BATCH_SIZE" \
MICRO_BATCH_SIZE="$MICRO_BATCH_SIZE" \
EVAL_BATCH_SIZE="$EVAL_BATCH_SIZE" \
N_SAMPLES_PER_PROMPT="$N_SAMPLES_PER_PROMPT" \
MAX_STEPS="$MAX_STEPS" \
GPU_MEMORY_UTILIZATION="$GPU_MEMORY_UTILIZATION" \
MAX_MODEL_LEN="$MAX_MODEL_LEN" \
PROJECT_NAME="$PROJECT_NAME" \
bash "$REPO_ROOT/scripts/server/run_ctf_rl_training.sh" \
  trainer.max_prompt_length="$TRAINER_MAX_PROMPT_LENGTH" \
  generator.max_input_length="$GENERATOR_MAX_INPUT_LENGTH" \
  generator.sampling_params.max_generate_length="$MAX_GENERATE_LENGTH" \
  generator.sampling_params.temperature="$TEMPERATURE" \
  "$@"
