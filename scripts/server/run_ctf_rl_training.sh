#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SKYRL_PATH="$REPO_ROOT/SkyRL/skyrl-train"
EZ_SRC="$REPO_ROOT/worker_orchestrator/ez_generator"
SYNC_TARGET="$SKYRL_PATH/vulrl_inside_skyrl_router"
LOG_DIR="$REPO_ROOT/logs/server"
OUTPUT_ROOT="$REPO_ROOT/outputs"

mkdir -p "$LOG_DIR" "$OUTPUT_ROOT/checkpoints" "$OUTPUT_ROOT/skyrl"

RUN_NAME="${RUN_NAME:-ctf_subtask_$(date +%Y%m%d_%H%M%S)}"
TRAIN_LOG="$LOG_DIR/train_${RUN_NAME}.log"
LATEST_TRAIN_LOG="$LOG_DIR/train_latest.log"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-$OUTPUT_ROOT/checkpoints/$RUN_NAME}"
HYDRA_OUTPUT_DIR="${HYDRA_OUTPUT_DIR:-$OUTPUT_ROOT/skyrl/$RUN_NAME}"
TRAIN_DATA="${TRAIN_DATA:-$REPO_ROOT/dataset/ctf_parquet/train_ctf_subtask_combined.parquet}"

MODEL_PATH="$REPO_ROOT/worker_orchestrator/qwen2.5-1.5b"
MODEL_NAME="${MODEL_NAME:-Qwen/Qwen2.5-1.5B}"
NUM_GPUS="${NUM_GPUS:-1}"
EPOCHS="${EPOCHS:-1}"
TRAIN_BATCH_SIZE="${TRAIN_BATCH_SIZE:-1}"
POLICY_MINI_BATCH_SIZE="${POLICY_MINI_BATCH_SIZE:-$TRAIN_BATCH_SIZE}"
MICRO_BATCH_SIZE="${MICRO_BATCH_SIZE:-1}"
EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-1}"
N_SAMPLES_PER_PROMPT="${N_SAMPLES_PER_PROMPT:-1}"
MAX_STEPS="${MAX_STEPS:-20}"
LEARNING_RATE="${LEARNING_RATE:-1e-6}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.5}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-131072}"
ROLLOUT_TIMEOUT="${ROLLOUT_TIMEOUT:-1800}"
POLL_INTERVAL="${POLL_INTERVAL:-10}"
HTTP_ENDPOINT_PORT="${HTTP_ENDPOINT_PORT:-17777}"
PROJECT_NAME="${PROJECT_NAME:-vulrl_ctf_subtask}"

ln -sfn "$TRAIN_LOG" "$LATEST_TRAIN_LOG"
exec > >(tee -a "$TRAIN_LOG") 2>&1

if [ ! -d "$SKYRL_PATH" ]; then
  echo "SkyRL path not found: $SKYRL_PATH"
  exit 1
fi

if [ ! -d "$EZ_SRC" ]; then
  echo "ez_generator path not found: $EZ_SRC"
  exit 1
fi

if [ ! -f "$TRAIN_DATA" ]; then
  echo "Training parquet not found: $TRAIN_DATA"
  echo "Run: bash $REPO_ROOT/scripts/server/convert_ctf_subtask_data.sh"
  exit 1
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found on PATH."
  exit 1
fi

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "python3/python not found on PATH."
  exit 1
fi

if ! "$PYTHON_BIN" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:12345/health', timeout=5).read()" >/dev/null 2>&1; then
  echo "Worker Router is not healthy at http://127.0.0.1:12345"
  echo "Run: bash $REPO_ROOT/scripts/server/start_worker_router_logged.sh"
  exit 1
fi

if [ -n "$MODEL_PATH" ] && [ -e "$MODEL_PATH" ]; then
  MODEL_TO_USE="$MODEL_PATH"
else
  MODEL_TO_USE="$MODEL_NAME"
fi

mkdir -p "$CHECKPOINT_DIR" "$HYDRA_OUTPUT_DIR"

echo "Syncing ez_generator into SkyRL package: $SYNC_TARGET"
rm -rf "$SYNC_TARGET"
mkdir -p "$SYNC_TARGET"
cp -R "$EZ_SRC"/. "$SYNC_TARGET"/

export PATH="$HOME/.local/bin:$PATH"
export PYTHONPATH="$SKYRL_PATH:${PYTHONPATH:-}"
export RAY_EXPERIMENTAL_NOSET_CUDA_VISIBLE_DEVICES=1
export WANDB_API_KEY="${WANDB_API_KEY:-dummy_key_for_local_logging}"
export WANDB_MODE=disabled

EXTRA_ENGINE_ARGS=()
if [ -n "$MAX_MODEL_LEN" ]; then
  EXTRA_ENGINE_ARGS+=(+generator.engine_init_kwargs.max_model_len="$MAX_MODEL_LEN")
fi

echo "============================================================"
echo "Run CTF RL Training"
echo "============================================================"
echo "Repo root: $REPO_ROOT"
echo "SkyRL path: $SKYRL_PATH"
echo "Sync target: $SYNC_TARGET"
echo "Train parquet: $TRAIN_DATA"
echo "Model: $MODEL_TO_USE"
echo "Run name: $RUN_NAME"
echo "Checkpoint dir: $CHECKPOINT_DIR"
echo "Hydra output dir: $HYDRA_OUTPUT_DIR"
echo "Training log: $TRAIN_LOG"
echo "Worker Router: http://127.0.0.1:12345"
echo "Local LLM endpoint port: $HTTP_ENDPOINT_PORT"
echo "Epochs: $EPOCHS"
echo "Train batch size: $TRAIN_BATCH_SIZE"
echo "Samples per prompt: $N_SAMPLES_PER_PROMPT"
echo "Max rollout steps: $MAX_STEPS"
echo "GPU count: $NUM_GPUS"
echo "GPU memory utilization: $GPU_MEMORY_UTILIZATION"
echo "Max model len override: ${MAX_MODEL_LEN:-<default>}"
echo "============================================================"
echo

cd "$SKYRL_PATH"

uv run --extra vllm \
  --with docker \
  --with requests \
  --with aiohttp \
  -m vulrl_inside_skyrl_router.main_vulrl_skyrl \
  data.train_data="['$TRAIN_DATA']" \
  data.val_data=null \
  trainer.algorithm.advantage_estimator=grpo \
  trainer.policy.model.path="$MODEL_TO_USE" \
  trainer.placement.colocate_all=true \
  trainer.strategy=fsdp2 \
  trainer.placement.policy_num_gpus_per_node="$NUM_GPUS" \
  trainer.placement.ref_num_gpus_per_node="$NUM_GPUS" \
  trainer.placement.policy_num_nodes=1 \
  trainer.placement.ref_num_nodes=1 \
  trainer.policy.sequence_parallel_size=1 \
  trainer.epochs="$EPOCHS" \
  trainer.eval_batch_size="$EVAL_BATCH_SIZE" \
  trainer.eval_before_train=false \
  trainer.eval_interval=-1 \
  trainer.update_epochs_per_batch=1 \
  trainer.train_batch_size="$TRAIN_BATCH_SIZE" \
  trainer.policy_mini_batch_size="$POLICY_MINI_BATCH_SIZE" \
  trainer.micro_forward_batch_size_per_gpu="$MICRO_BATCH_SIZE" \
  trainer.micro_train_batch_size_per_gpu="$MICRO_BATCH_SIZE" \
  trainer.dump_data_batch=true \
  trainer.ckpt_interval=10 \
  trainer.max_prompt_length=2048 \
  trainer.policy.optimizer_config.lr="$LEARNING_RATE" \
  trainer.algorithm.use_kl_loss=true \
  trainer.logger=console \
  trainer.project_name="$PROJECT_NAME" \
  trainer.run_name="$RUN_NAME" \
  trainer.resume_mode=null \
  trainer.ckpt_path="$CHECKPOINT_DIR" \
  generator.backend=vllm \
  generator.run_engines_locally=true \
  generator.enable_http_endpoint=true \
  generator.http_endpoint_host=127.0.0.1 \
  generator.http_endpoint_port="$HTTP_ENDPOINT_PORT" \
  generator.async_engine=true \
  generator.batched=true \
  generator.num_inference_engines="$NUM_GPUS" \
  generator.inference_engine_tensor_parallel_size=1 \
  generator.n_samples_per_prompt="$N_SAMPLES_PER_PROMPT" \
  generator.max_turns="$MAX_STEPS" \
  generator.max_input_length=4096 \
  generator.sampling_params.max_generate_length=2048 \
  generator.sampling_params.logprobs=null \
  generator.gpu_memory_utilization="$GPU_MEMORY_UTILIZATION" \
  +generator.rollout_timeout="$ROLLOUT_TIMEOUT" \
  +generator.poll_interval="$POLL_INTERVAL" \
  hydra.run.dir="$HYDRA_OUTPUT_DIR" \
  "${EXTRA_ENGINE_ARGS[@]}" \
  "$@"

echo
echo "Training finished."
echo "Training log: $TRAIN_LOG"
echo "Checkpoint dir: $CHECKPOINT_DIR"
echo "Hydra output dir: $HYDRA_OUTPUT_DIR"
echo "Worker Router log: $REPO_ROOT/worker_orchestrator/logs/worker_router.log"
