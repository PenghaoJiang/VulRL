#!/bin/bash
set -e  # Exit on error

# =============================================================================
# VulRL SkyRL Training Launcher
# =============================================================================
# This script:
# 1. Syncs ez_generator code to SkyRL directory structure
# 2. Sets up environment variables
# 3. Launches SkyRL training with EzVulRLGenerator (Worker Router based)
#
# IMPORTANT PREREQUISITE:
#   Worker Router MUST be running at http://localhost:5000 (hardcoded)
#   If running on a remote machine, use SSH port forwarding:
#     ssh -L 5000:remote-host:5000 remote-host
#
# Usage:
#   bash run_vulrl_skyrl.sh
#
# Configuration:
#   Edit variables below or set via environment before running
# =============================================================================

# -----------------------------------------------------------------------------
# Configuration Variables (Edit these for your setup)
# -----------------------------------------------------------------------------

# Model configuration
MODEL_PATH="${MODEL_PATH:-/data1/jph/VulRL/models/qwen2.5-1.5b}"
MODEL_NAME="${MODEL_NAME:-qwen2.5-1.5b}"

# -----------------------------------------------------------------------------
# DUAL INFERENCE ARCHITECTURE
# -----------------------------------------------------------------------------
# This script uses TWO separate LLM inference systems:
#
# 1. LOCAL VLLM (for SkyRL policy training):
#    - Runs within SkyRL on GPU (generator.run_engines_locally=True)
#    - Used for policy gradient updates and sampling
#    - Scales with NUM_GPUS (generator.num_inference_engines=$NUM_GPUS)
#    - Memory controlled by GPU_MEMORY_UTILIZATION
#
# 2. REMOTE LLM (for Worker Router rollouts):
#    - External LLM server used by Worker Router for vulnerability exploitation
#    - Configured directly in Worker Router (not passed via this script)
#    - Used during rollout execution (not training)
# -----------------------------------------------------------------------------

# Worker Router configuration
# IMPORTANT: Worker Router URL is HARDCODED to http://localhost:12345 in WorkerRouterClient
# It is NOT configurable via this script or Hydra config
# If Worker Router runs on a different host/port, use SSH port forwarding:
#   ssh -L 12345:remote-host:12345 remote-host
WORKER_ROUTER_URL="http://localhost:12345"  # Hardcoded (for display only)

# Training data (fixed path as requested)
TRAIN_DATA="${TRAIN_DATA:-/data1/jph/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/train.parquet}"

# Training parameters - MINIMAL FOR TESTING
EPOCHS="${EPOCHS:-1}"                      # 1 epoch
TRAIN_BATCH_SIZE="${TRAIN_BATCH_SIZE:-3}" # 3 parallel tasks
EVAL_BATCH_SIZE="${EVAL_BATCH_SIZE:-3}"   # 3 parallel eval tasks
MAX_STEPS="${MAX_STEPS:-10}"              # Max steps per rollout
LEARNING_RATE="${LEARNING_RATE:-1e-6}"

# System configuration (from run_training.sh)
# NUM_GPUS: Set to 0 for CPU-only training (when GPU is busy/saturated)
#           Set to 1+ for GPU training (much faster, requires free GPU)
# Check GPU availability: nvidia-smi
NUM_GPUS="${NUM_GPUS:-1}"
CHECKPOINT_DIR="${CHECKPOINT_DIR:-/data1/jph/ckpts/vulrl_skyrl_test}"

# GPU Memory Configuration
# VLLM gpu_memory_utilization: fraction of GPU memory to use for inference engine
# For 10GB on 98GB GPU: 10/98 ≈ 0.10
# For 15GB on 98GB GPU: 15/98 ≈ 0.15
# Default 0.15 (~15GB) - adjust based on available memory
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.15}"

# Logging
LOGGER="${LOGGER:-local}"  # Options: local, wandb, tensorboard
PROJECT_NAME="${PROJECT_NAME:-vulrl_skyrl}"
RUN_NAME="${RUN_NAME:-vulrl_test_$(date +%Y%m%d_%H%M%S)}"

# Path configuration (CRITICAL - these must match your remote machine)
WORKER_ORCHESTRATOR_PATH="/data1/jph/VulRL/worker_orchestrator"
EZ_GENERATOR_PATH="$WORKER_ORCHESTRATOR_PATH/ez_generator"
SKYRL_PATH="/data1/jph/VulRL/SkyRL/skyrl-train"
VULRL_INSIDE_SKYRL_PATH="$SKYRL_PATH/vulrl_inside_skyrl_v2"

# -----------------------------------------------------------------------------
# Header
# -----------------------------------------------------------------------------

echo "============================================================"
echo "VulRL SkyRL Training Launcher"
echo "============================================================"
echo ""
echo "Configuration:"
echo "  Model: $MODEL_PATH"
echo "  Training Data: $TRAIN_DATA"
echo ""
echo "Inference Setup (Dual Mode):"
echo "  - SkyRL Inference: Local VLLM on GPU (for policy training)"
echo "  - Worker Router: $WORKER_ROUTER_URL (for rollout execution)"
echo ""
echo "Training Parameters:"
echo "  Epochs: $EPOCHS"
echo "  Batch Size: $TRAIN_BATCH_SIZE"
echo "  Max Steps per Rollout: $MAX_STEPS"
echo "  Training GPUs: $NUM_GPUS (0=CPU, 1+=GPU)"
echo "  Inference Engines: $NUM_GPUS"
echo "  GPU Memory Utilization: $GPU_MEMORY_UTILIZATION"
echo "  Checkpoint Dir: $CHECKPOINT_DIR"
echo "============================================================"
echo ""

# -----------------------------------------------------------------------------
# Step 1: Sync Code to SkyRL Directory
# -----------------------------------------------------------------------------

echo "Step 1: Syncing ez_generator code to SkyRL structure..."
echo ""

# Check if source directory exists
if [ ! -d "$EZ_GENERATOR_PATH" ]; then
    echo "ERROR: ez_generator directory not found at: $EZ_GENERATOR_PATH"
    echo "Please check the path configuration."
    exit 1
fi

# Create target directory if it doesn't exist
mkdir -p "$VULRL_INSIDE_SKYRL_PATH"

# Clear existing files in target directory
echo "  - Clearing existing files in: $VULRL_INSIDE_SKYRL_PATH"
rm -rf "${VULRL_INSIDE_SKYRL_PATH:?}"/*

# Copy all files from ez_generator to target
echo "  - Copying files from: $EZ_GENERATOR_PATH"
echo "                    to: $VULRL_INSIDE_SKYRL_PATH"
cp -r "$EZ_GENERATOR_PATH"/* "$VULRL_INSIDE_SKYRL_PATH/"

# Verify critical files exist
if [ ! -f "$VULRL_INSIDE_SKYRL_PATH/main_vulrl_skyrl.py" ]; then
    echo "ERROR: main_vulrl_skyrl.py not found after copy"
    exit 1
fi
if [ ! -f "$VULRL_INSIDE_SKYRL_PATH/ez_vulrl_generator.py" ]; then
    echo "ERROR: ez_vulrl_generator.py not found after copy"
    exit 1
fi

echo "✓ Code sync complete"
echo ""

# -----------------------------------------------------------------------------
# Step 2: Check Prerequisites
# -----------------------------------------------------------------------------

echo "Step 2: Checking prerequisites..."
echo ""

# Check training data
if [ ! -f "$TRAIN_DATA" ]; then
    echo "WARNING: Training data not found at: $TRAIN_DATA"
    echo "You can create test data with:"
    echo "  python $VULRL_INSIDE_SKYRL_PATH/create_parquet.py --create-test --output $TRAIN_DATA"
    echo ""
    read -p "Would you like to create test data now? (y/n) " -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        cd "$SKYRL_PATH"
        uv run --with pandas --with pyarrow python \
            "$VULRL_INSIDE_SKYRL_PATH/create_parquet.py" \
            --create-test \
            --output "$TRAIN_DATA"
        echo "✓ Test data created"
    else
        echo "ERROR: Cannot proceed without training data"
        exit 1
    fi
fi

echo "✓ Training data exists: $TRAIN_DATA"

# Check model path
if [ -d "$MODEL_PATH" ]; then
    echo "✓ Model exists: $MODEL_PATH"
    MODEL_TO_USE="$MODEL_PATH"
elif [ -f "$MODEL_PATH/config.json" ]; then
    echo "✓ Model exists: $MODEL_PATH"
    MODEL_TO_USE="$MODEL_PATH"
else
    echo "⚠ Model not found at: $MODEL_PATH"
    echo "  Will use model name for HuggingFace download: $MODEL_NAME"
    MODEL_TO_USE="$MODEL_NAME"
fi

# Check checkpoint directory
mkdir -p "$CHECKPOINT_DIR"
echo "✓ Checkpoint directory ready: $CHECKPOINT_DIR"

echo ""

# -----------------------------------------------------------------------------
# Step 3: Setup Environment
# -----------------------------------------------------------------------------

echo "Step 3: Setting up environment..."
echo ""

# Ray configuration - allow GPU sharing
export RAY_EXPERIMENTAL_NOSET_CUDA_VISIBLE_DEVICES=1

# CUDA configuration
export CUDA_VISIBLE_DEVICES=0

# WandB configuration (disable for local logging)
export WANDB_API_KEY="${WANDB_API_KEY:-dummy_key_for_local_logging}"
export WANDB_MODE="disabled"

# Add skyrl-train to PYTHONPATH so imports work
export PYTHONPATH="$SKYRL_PATH:${PYTHONPATH}"

echo "✓ Environment configured"
echo "  PYTHONPATH: $PYTHONPATH"
echo "  CUDA_VISIBLE_DEVICES: $CUDA_VISIBLE_DEVICES"
echo "  Training GPUs: $NUM_GPUS"
echo "  Inference Engines: $NUM_GPUS (local VLLM)"
echo "  GPU Memory Utilization: ${GPU_MEMORY_UTILIZATION}"
echo ""

# -----------------------------------------------------------------------------
# Step 4: Navigate to SkyRL Directory
# -----------------------------------------------------------------------------

echo "Step 4: Navigating to SkyRL directory..."
cd "$SKYRL_PATH"
echo "✓ Current directory: $(pwd)"
echo ""

# -----------------------------------------------------------------------------
# Step 5: Launch Training
# -----------------------------------------------------------------------------

echo "============================================================"
echo "Launching SkyRL Training with VulRL Generator"
echo "============================================================"
echo ""
echo "Rollout Execution: Worker Router at $WORKER_ROUTER_URL"
echo "Policy Training: Local VLLM on GPU"
echo ""
echo "Press Ctrl+C to stop training"
echo ""
echo "============================================================"
echo ""

# Launch training with uv
# Note: We run from skyrl-train directory and reference the module as vulrl_inside_skyrl_v2
uv run --extra vllm \
  --with docker \
  --with requests \
  --with aiohttp \
  -m vulrl_inside_skyrl_v2.main_vulrl_skyrl \
  data.train_data="['$TRAIN_DATA']" \
  data.val_data=null \
  trainer.algorithm.advantage_estimator="grpo" \
  trainer.policy.model.path="$MODEL_TO_USE" \
  trainer.placement.colocate_all=true \
  trainer.strategy=fsdp2 \
  trainer.placement.policy_num_gpus_per_node=$NUM_GPUS \
  trainer.placement.ref_num_gpus_per_node=$NUM_GPUS \
  trainer.placement.policy_num_nodes=1 \
  trainer.placement.ref_num_nodes=1 \
  trainer.policy.sequence_parallel_size=1 \
  generator.num_inference_engines=$NUM_GPUS \
  generator.inference_engine_tensor_parallel_size=1 \
  trainer.epochs=$EPOCHS \
  trainer.eval_batch_size=$EVAL_BATCH_SIZE \
  trainer.eval_before_train=false \
  trainer.eval_interval=-1 \
  trainer.update_epochs_per_batch=1 \
  trainer.train_batch_size=$TRAIN_BATCH_SIZE \
  trainer.policy_mini_batch_size=$TRAIN_BATCH_SIZE \
  trainer.micro_forward_batch_size_per_gpu=1 \
  trainer.micro_train_batch_size_per_gpu=1 \
  trainer.dump_data_batch=true \
  trainer.ckpt_interval=10 \
  trainer.max_prompt_length=2048 \
  generator.sampling_params.max_generate_length=2048 \
  generator.sampling_params.logprobs=null \
  generator.max_input_length=4096 \
  generator.max_turns=$MAX_STEPS \
  trainer.policy.optimizer_config.lr=$LEARNING_RATE \
  trainer.algorithm.use_kl_loss=true \
  generator.backend=vllm \
  generator.run_engines_locally=True \
  generator.enable_http_endpoint=False \
  generator.async_engine=true \
  generator.batched=true \
  generator.n_samples_per_prompt=1 \
  generator.gpu_memory_utilization="$GPU_MEMORY_UTILIZATION" \
  trainer.logger="$LOGGER" \
  trainer.project_name="$PROJECT_NAME" \
  trainer.run_name="$RUN_NAME" \
  trainer.resume_mode=null \
  trainer.ckpt_path="$CHECKPOINT_DIR" \
  "$@"

echo ""
echo "============================================================"
echo "Training completed!"
echo "============================================================"
echo ""
echo "Checkpoints saved to: $CHECKPOINT_DIR"
echo "Logs available in: $SKYRL_PATH/outputs/"
echo ""
