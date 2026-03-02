#!/bin/bash
set -e  # Exit on error

# =============================================================================
# VulRL Security Exploitation Training Launcher
# =============================================================================
# This script:
# 1. Checks prerequisites (Ray, Docker, Python packages)
# 2. Builds Docker attacker image if needed
# 3. Sets up environment variables
# 4. Launches SkyRL training with VulRL SecurityEnv
#
# Usage:
#   bash run_training.sh
#
# Configuration:
#   Edit variables below or set via environment before running
# =============================================================================

# Add uv to PATH
export PATH="$HOME/.local/bin:$PATH"

# Cleanup function - runs on exit (success or failure)
cleanup() {
    echo ""
    echo "Cleaning up..."
    # Stop Ray if it was started by this script
    ray stop 2>/dev/null || true
    echo "✓ Cleanup complete"
}
trap cleanup EXIT

echo "============================================================"
echo "VulRL Security Training Launcher"
echo "============================================================"

# -----------------------------------------------------------------------------
# Configuration (can be overridden via environment variables)
# -----------------------------------------------------------------------------

# Model configuration
: "${MODEL_PATH:=/data1/jph/models/Qwen2.5-1.5B-Instruct}"  # Local model path
: "${MODEL_NAME:=Qwen/Qwen2.5-1.5B-Instruct}"  # Fallback to HF auto-download

# Training data (create minimal test data if not provided)
# Use absolute path so Ray workers can find it
: "${TRAIN_DATA:=/data1/jph/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/train.parquet}"

# Training parameters - MINIMAL FOR TESTING
: "${EPOCHS:=1}"                    # Just 1 epoch for workflow test
: "${TRAIN_BATCH_SIZE:=1}"          # Minimal batch size
: "${ROLLOUTS_PER_TASK:=2}"         # 2 rollouts per task
: "${MAX_TURNS:=10}"                # Reduced from 30 to 10 for faster testing
: "${LEARNING_RATE:=1e-6}"

# System configuration
: "${NUM_GPUS:=1}"
: "${CHECKPOINT_DIR:=/data1/jph/ckpts/vulrl_test}"
: "${INFERENCE_BACKEND:=vllm}"

# Logging
: "${LOGGER:=local}"  # Options: local, wandb, tensorboard

# -----------------------------------------------------------------------------
# Prerequisite Checks
# -----------------------------------------------------------------------------

echo ""
echo "Checking prerequisites..."
echo ""

# Check Python (try python3 first, then python)
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
    echo "✓ Python: $(python3 --version)"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
    echo "✓ Python: $(python --version)"
else
    echo "ERROR: Python not found (tried python3 and python)"
    exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker not found"
    exit 1
fi
echo "✓ Docker: $(docker --version)"

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo "ERROR: Docker daemon not running"
    echo "Start Docker with: sudo systemctl start docker"
    exit 1
fi
echo "✓ Docker daemon: running"

# Check Ray
if ! $PYTHON_CMD -c "import ray" &> /dev/null; then
    echo "WARNING: Ray not found in current environment"
    echo "Will be installed via uv during training"
else
    echo "✓ Ray: $($PYTHON_CMD -c 'import ray; print(ray.__version__)')"
    
    # Check if Ray is already running
    if $PYTHON_CMD -c "import ray; ray.is_initialized()" 2>/dev/null; then
        echo "⚠ Ray is already running - stopping for clean state"
        ray stop 2>/dev/null || true
        echo "✓ Ray stopped"
    fi
fi

# Check model path
if [ -d "$MODEL_PATH" ]; then
    echo "✓ Model: $MODEL_PATH (local)"
    MODEL_TO_USE="$MODEL_PATH"
elif [ -f "$MODEL_PATH/config.json" ]; then
    echo "✓ Model: $MODEL_PATH (local)"
    MODEL_TO_USE="$MODEL_PATH"
else
    echo "⚠ Local model not found at $MODEL_PATH"
    echo "  Will download from HuggingFace: $MODEL_NAME"
    MODEL_TO_USE="$MODEL_NAME"
fi

# -----------------------------------------------------------------------------
# Build Docker Attacker Image
# -----------------------------------------------------------------------------

echo ""
echo "Checking Docker attacker image..."
echo ""

if docker images | grep -q "cve-attacker.*latest"; then
    echo "✓ Attacker image exists: cve-attacker:latest"
else
    echo "Building attacker image..."
    
    # Create temporary Dockerfile
    TMPDIR=$(mktemp -d)
    cat > "$TMPDIR/Dockerfile" << 'EOF'
FROM python:3.11-slim
RUN apt-get update && apt-get install -y \
    curl wget netcat-traditional nmap dnsutils iputils-ping \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir requests
WORKDIR /attacker
CMD ["tail", "-f", "/dev/null"]
EOF
    
    docker build -t cve-attacker:latest "$TMPDIR"
    rm -rf "$TMPDIR"
    echo "✓ Attacker image built"
fi

# -----------------------------------------------------------------------------
# Prepare Training Data (Create Minimal Test Data)
# -----------------------------------------------------------------------------

echo ""
echo "Preparing training data..."
echo ""

if [ ! -f "$TRAIN_DATA" ]; then
    echo "Creating minimal test data at $TRAIN_DATA"
    
    # Create temporary Python script
    cat > /tmp/create_test_data.py << 'PYTHON_SCRIPT'
import pandas as pd
import json

# Create minimal test data with 2 CVE tasks
data = [
    {
        "task_id": "CVE-2024-TEST-1",
        "task_type": "cvebench",
        "cve_id": "CVE-2024-TEST-1",
        "prompt": "You are a security researcher testing a web application vulnerability. Analyze and exploit the target service.",
        "target_info": {"service": "test-web-app", "port": 8080}
    },
    {
        "task_id": "CVE-2024-TEST-2",
        "task_type": "cvebench",
        "cve_id": "CVE-2024-TEST-2",
        "prompt": "Test SQL injection vulnerability in the authentication system.",
        "target_info": {"service": "test-db-app", "port": 3306}
    }
]

df = pd.DataFrame(data)
import os
output_path = os.path.abspath("./test_data.parquet")
df.to_parquet(output_path, index=False)
print(f"✓ Created test data with {len(df)} tasks at {output_path}")
PYTHON_SCRIPT
    
    # Run with uv to get pandas
    uv run --with pandas --with pyarrow $PYTHON_CMD /tmp/create_test_data.py
    rm /tmp/create_test_data.py
fi

echo "✓ Training data ready: $TRAIN_DATA"

# -----------------------------------------------------------------------------
# Setup Environment Variables
# -----------------------------------------------------------------------------

echo ""
echo "Setting up environment..."
echo ""

# Ray configuration - allow GPU sharing
export RAY_EXPERIMENTAL_NOSET_CUDA_VISIBLE_DEVICES=1

# CUDA configuration
export CUDA_VISIBLE_DEVICES=0

# WandB configuration - set dummy key to bypass validation (we use local logging)
export WANDB_API_KEY="${WANDB_API_KEY:-dummy_key_for_local_logging}"
export WANDB_MODE="disabled"  # Disable WandB completely

# Checkpoint directory
mkdir -p "$CHECKPOINT_DIR"
echo "✓ Checkpoint directory: $CHECKPOINT_DIR"

# Add current directory to PYTHONPATH so vulrl module can be found
export PYTHONPATH="$(pwd):${PYTHONPATH}"
echo "✓ PYTHONPATH: $PYTHONPATH"

# -----------------------------------------------------------------------------
# Docker Cleanup (before starting training)
# -----------------------------------------------------------------------------

echo ""
echo "Cleaning up old Docker resources..."
# Stop and remove all containers with "vulhub" or "vulpoc" in their name
docker ps -a --format "{{.ID}} {{.Names}}" | grep -E "vulhub|vulpoc" | awk '{print $1}' | xargs -r docker stop
docker ps -a --format "{{.ID}} {{.Names}}" | grep -E "vulhub|vulpoc" | awk '{print $1}' | xargs -r docker rm
# Remove networks created by vulhub/vulpoc (excluding default/app networks)
docker network ls --format "{{.ID}} {{.Name}}" | grep -E "vulhub|vulpoc" | awk '{print $1}' | xargs -r docker network rm
# Prune unused networks (excluding default/app networks)
docker network prune -f --filter "until=24h" --filter "label!=com.docker.compose.project" --filter "name!=bridge" --filter "name!=host" --filter "name!=none" --filter "name!=my-tech-blog_tech-blog-network" --filter "name!=supabase_network_SolarDemo"
echo "✓ Docker cleanup complete"

# -----------------------------------------------------------------------------
# Launch Training
# -----------------------------------------------------------------------------

echo ""
echo "============================================================"
echo "Launching Training"
echo "============================================================"
echo ""
echo "Configuration:"
echo "  Model: $MODEL_TO_USE"
echo "  Data: $TRAIN_DATA"
echo "  Epochs: $EPOCHS"
echo "  Batch Size: $TRAIN_BATCH_SIZE"
echo "  Max Turns: $MAX_TURNS"
echo "  Checkpoint: $CHECKPOINT_DIR"
echo ""
echo "============================================================"
echo ""

# Build the uv run command with all Hydra parameters
# Use --directory to reference parent skyrl-train project (which has vllm extra defined)
uv run --directory .. --extra $INFERENCE_BACKEND \
  --with docker \
  --with requests \
  --with Pillow \
  python vulrl_inside_skyrl/main_training.py \
  ++data.train_data="['$TRAIN_DATA']" \
  ++data.val_data=null \
  ++trainer.algorithm.name=grpo \
  ++trainer.algorithm.advantage_estimator=rloo \
  ++trainer.algorithm.kl_coef=0.0 \
  ++trainer.algorithm.entropy_coef=0.0 \
  ++trainer.algorithm.normalize_advantage=False \
  ++trainer.train_batch_size=$TRAIN_BATCH_SIZE \
  ++trainer.policy_mini_batch_size=$TRAIN_BATCH_SIZE \
  ++trainer.rollout_batch_size=$TRAIN_BATCH_SIZE \
  ++trainer.rollouts_per_task=$ROLLOUTS_PER_TASK \
  ++trainer.learning_rate=$LEARNING_RATE \
  ++trainer.epochs=$EPOCHS \
  ++trainer.eval_interval=-1 \
  ++trainer.ckpt_path=$CHECKPOINT_DIR \
  ++trainer.resume_mode=latest \
  ++trainer.save_interval=100 \
  ++trainer.policy.model.path=$MODEL_TO_USE \
  ++trainer.policy.model.lora.rank=8 \
  ++trainer.policy.model.lora.alpha=16 \
  ++trainer.policy.model.lora.dropout=0.05 \
  ++trainer.policy.model.lora.target_modules=all-linear \
  ++trainer.placement.colocate_all=true \
  ++trainer.placement.policy_num_nodes=1 \
  ++trainer.placement.policy_num_gpus_per_node=$NUM_GPUS \
  ++trainer.placement.ref_num_nodes=1 \
  ++trainer.placement.ref_num_gpus_per_node=$NUM_GPUS \
  ++trainer.placement.critic_num_nodes=1 \
  ++trainer.placement.critic_num_gpus_per_node=$NUM_GPUS \
  ++trainer.placement.reward_num_nodes=1 \
  ++trainer.placement.reward_num_gpus_per_node=$NUM_GPUS \
  ++generator.num_inference_engines=$NUM_GPUS \
  ++generator.inference_backend=$INFERENCE_BACKEND \
  ++generator.inference_engine_tensor_parallel_size=1 \
  ++generator.gpu_memory_utilization=0.40 \
  ++generator.max_turns=$MAX_TURNS \
  +generator.engine_init_kwargs.max_model_len=2048 \
  +generator.engine_init_kwargs.enable_chunked_prefill=False \
  ++dispatcher.strategy=async_pipeline \
  ++logging.backend=$LOGGER

echo ""
echo "============================================================"
echo "Training completed!"
echo "============================================================"
