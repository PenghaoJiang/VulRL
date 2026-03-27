# VulRL SkyRL Integration Guide

Complete guide for training VulRL models using SkyRL with Worker Router architecture.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [File Structure](#file-structure)
- [Setup Instructions](#setup-instructions)
- [Running Training](#running-training)
- [Creating Training Data](#creating-training-data)
- [Configuration](#configuration)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

---

## Overview

This integration allows VulRL to leverage SkyRL's PPO training framework while using the Worker Router architecture for distributed rollout execution.

### Key Features

- ✅ **Distributed Execution**: Rollouts run on auto-scaled Worker Units
- ✅ **Parallel Processing**: Multiple tasks execute simultaneously
- ✅ **Docker Isolation**: Each rollout runs in isolated Docker environments
- ✅ **LLM Integration**: Connects to vLLM server for model inference
- ✅ **SkyRL Compatible**: Drop-in generator replacement

### How It Works

```
SkyRL Trainer → EzVulRLGenerator → Worker Router → Worker Units → Docker + LLM
     (PPO)         (HTTP Client)      (FastAPI)      (Subprocess)   (Vulhub + vLLM)
```

1. **SkyRL**: Manages PPO training loop, model updates, checkpoints
2. **EzVulRLGenerator**: Submits rollout requests to Worker Router via HTTP
3. **Worker Router**: Queues tasks, manages worker pool, auto-scales
4. **Worker Units**: Execute rollouts (Docker + LLM interaction)
5. **Results**: Flow back through Redis → Worker Router → Generator → SkyRL

---

## Quick Start

### Prerequisites

```bash
# On remote machine (/data1/jph/)

# 1. Start Redis
redis-server --daemonize yes

# 2. Start Worker Router
cd /data1/jph/VulRL/worker_orchestrator
source venv/bin/activate
python worker_router/main.py &

# 3. Start LLM Server (if not already running)
cd /data1/jph
bash start_llm_server.sh  # Your existing script

# 4. Verify all services
curl http://localhost:5000/health         # Worker Router
curl http://localhost:30000/v1/models     # LLM Server
redis-cli ping                            # Redis
```

### Run Training

```bash
cd /data1/jph/VulRL/worker_orchestrator/ez_generator
bash run_vulrl_skyrl.sh
```

That's it! The script will:
1. Sync code to SkyRL directory structure
2. Check prerequisites
3. Create test data if needed
4. Launch training with minimal settings (1 epoch, 3 parallel tasks)

---

## Architecture

### Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                      SkyRL Training                             │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  main_vulrl_skyrl.py (VulrlPPOExp)                       │  │
│  │  ├─ Hydra config loading                                 │  │
│  │  ├─ Ray initialization                                    │  │
│  │  └─ PPO training loop                                     │  │
│  └──────────────────┬───────────────────────────────────────┘  │
│                     │                                           │
│  ┌──────────────────▼───────────────────────────────────────┐  │
│  │  EzVulRLGenerator                                         │  │
│  │  ├─ Inherits from SkyRLGymGenerator                       │  │
│  │  ├─ WorkerRouterClient (HTTP)                            │  │
│  │  ├─ Active polling for results                           │  │
│  │  └─ Converts trajectories to SkyRL format               │  │
│  └──────────────────┬───────────────────────────────────────┘  │
└────────────────────────┼───────────────────────────────────────┘
                         │ HTTP
                         │
┌────────────────────────▼───────────────────────────────────────┐
│                   Worker Router (FastAPI)                       │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  routes/rollout.py                                       │  │
│  │  ├─ POST /api/rollout/submit  → Queue task              │  │
│  │  ├─ GET  /api/rollout/status  → Check status            │  │
│  │  └─ GET  /api/rollout/result  → Retrieve result         │  │
│  └──────────────────┬───────────────────────────────────────┘  │
│                     │                                           │
│  ┌──────────────────▼───────────────────────────────────────┐  │
│  │  worker_pool.py                                          │  │
│  │  ├─ Auto-scaling logic                                   │  │
│  │  ├─ spawn_worker() → subprocess.Popen()                  │  │
│  │  └─ get_available_worker()                              │  │
│  └──────────────────────────────────────────────────────────┘  │
└────────────────────────┬───────────────────────────────────────┘
                         │ Redis
                         │
┌────────────────────────▼───────────────────────────────────────┐
│                         Redis                                   │
│  ├─ rollout:queue:{worker_id}  (Task queue)                   │
│  ├─ task:{task_id}              (Metadata)                     │
│  ├─ result:{task_id}            (Results)                      │
│  └─ worker:{worker_id}          (Status)                       │
└────────────────────────┬───────────────────────────────────────┘
                         │ BRPOP
                         │
┌────────────────────────▼───────────────────────────────────────┐
│                    Worker Units (Subprocesses)                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  main.py (Polling loop)                                  │  │
│  │  └─ rollout_executor.py                                  │  │
│  │     ├─ security_env.py (Gymnasium)                       │  │
│  │     │  └─ vulhub_adapter.py (subprocess Docker)          │  │
│  │     └─ agent_loop.py (LLM interaction)                   │  │
│  └───────────┬──────────────────────────────────────────────┘  │
└──────────────┼──────────────────────────────────────────────────┘
               │
       ┌───────┴────────┐
       │                │
┌──────▼─────┐   ┌──────▼──────┐
│   Docker   │   │  LLM Server │
│  (Vulhub)  │   │   (vLLM)    │
└────────────┘   └─────────────┘
```

---

## File Structure

```
ez_generator/
├── main_vulrl_skyrl.py          # SkyRL entry point (VulrlPPOExp)
├── ez_vulrl_generator.py        # Generator implementation
├── worker_router_client.py      # HTTP client for Worker Router
├── create_parquet.py            # Data converter
├── run_vulrl_skyrl.sh           # Training launcher script
├── SKYRL_INTEGRATION.md         # This file
└── README.md                    # General README

After running, synced to:
/data1/jph/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl_v2/
└── (same files as above)
```

---

## Setup Instructions

### 1. Install Dependencies

```bash
cd /data1/jph/VulRL/worker_orchestrator
source venv/bin/activate

# Core dependencies (if not already installed)
pip install -r requirements.txt

# Additional for SkyRL (installed via uv during training)
# - ray
# - torch
# - transformers
# - pandas
# - pyarrow
```

### 2. Prepare Model

```bash
# Option A: Use local model (recommended for speed)
MODEL_PATH="/data1/jph/models/qwen2.5-1.5b"

# Option B: HuggingFace auto-download
MODEL_NAME="Qwen/Qwen2.5-1.5B-Instruct"

# Verify model exists
ls -lh $MODEL_PATH/
# Should see: config.json, tokenizer.json, pytorch_model.bin, etc.
```

### 3. Create Training Data

```bash
cd /data1/jph/VulRL/worker_orchestrator/ez_generator

# Option A: Create test data
python create_parquet.py \
    --create-test \
    --output /data1/jph/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/train.parquet

# Option B: Convert from JSON
python create_parquet.py \
    --input my_tasks.json \
    --data-source json \
    --output /data1/jph/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/train.parquet
```

**Data Format** (JSON):
```json
[
    {
        "cve_id": "CVE-2024-28752",
        "vulhub_path": "/data1/jph/vulhub/apache-cxf/CVE-2024-28752",
        "prompt": "Exploit the Apache CXF vulnerability...",
        "max_steps": 10
    },
    {
        "cve_id": "CVE-2023-12345",
        "vulhub_path": "/data1/jph/vulhub/test-app/CVE-2023-12345",
        "prompt": "Test SQL injection vulnerability...",
        "max_steps": 15
    }
]
```

### 4. Start Services

```bash
# Terminal 1: Redis (if not already running)
redis-server --daemonize yes

# Terminal 2: Worker Router
cd /data1/jph/VulRL/worker_orchestrator
source venv/bin/activate
python worker_router/main.py

# Terminal 3: LLM Server (if not already running)
cd /data1/jph
bash start_llm_server.sh
# or
vllm serve /path/to/model \
    --host 0.0.0.0 \
    --port 30000 \
    --tensor-parallel-size 1 \
    --max-model-len 4096

# Verify all services are up
curl http://localhost:5000/health
curl http://localhost:30000/v1/models
redis-cli ping
```

---

## Running Training

### Basic Usage

```bash
cd /data1/jph/VulRL/worker_orchestrator/ez_generator
bash run_vulrl_skyrl.sh
```

### With Custom Configuration

```bash
# Set environment variables before running
export MODEL_PATH="/data1/jph/models/qwen2.5-1.5b"
export WORKER_ROUTER_URL="http://localhost:5000"
export LLM_ENDPOINT_HOST="localhost"
export LLM_ENDPOINT_PORT="30000"
export TRAIN_DATA="/path/to/train.parquet"
export EPOCHS=5
export TRAIN_BATCH_SIZE=8
export MAX_STEPS=20
export CHECKPOINT_DIR="/data1/jph/ckpts/vulrl_production"

bash run_vulrl_skyrl.sh
```

### Script Workflow

The `run_vulrl_skyrl.sh` script performs these steps:

1. **Code Sync**:
   ```bash
   rm -rf /data1/jph/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl_v2/*
   cp -r /data1/jph/VulRL/worker_orchestrator/ez_generator/* \
         /data1/jph/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl_v2/
   ```

2. **Prerequisites Check**:
   - Verify training data exists
   - Check model path
   - Create checkpoint directory

3. **Environment Setup**:
   ```bash
   export RAY_EXPERIMENTAL_NOSET_CUDA_VISIBLE_DEVICES=1
   export CUDA_VISIBLE_DEVICES=0
   export PYTHONPATH="/data1/jph/VulRL/SkyRL/skyrl-train:$PYTHONPATH"
   ```

4. **Launch Training**:
   ```bash
   uv run --extra vllm \
     -m vulrl_inside_skyrl_v2.main_vulrl_skyrl \
     data.train_data="['/path/to/train.parquet']" \
     generator.worker_router_url="http://localhost:5000" \
     generator.http_endpoint_host="localhost" \
     generator.http_endpoint_port=30000 \
     trainer.epochs=1 \
     trainer.train_batch_size=3 \
     ...
   ```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `MODEL_PATH` | `/data1/jph/models/qwen2.5-1.5b` | Local model path |
| `MODEL_NAME` | `qwen2.5-1.5b` | Model name for logging |
| `WORKER_ROUTER_URL` | `http://localhost:5000` | Worker Router API endpoint |
| `LLM_ENDPOINT_HOST` | `localhost` | LLM server host |
| `LLM_ENDPOINT_PORT` | `30000` | LLM server port |
| `TRAIN_DATA` | `/data1/jph/.../train.parquet` | Training data path |
| `EPOCHS` | `1` | Number of training epochs |
| `TRAIN_BATCH_SIZE` | `3` | Batch size (parallel tasks) |
| `MAX_STEPS` | `10` | Max steps per rollout |
| `LEARNING_RATE` | `1e-6` | Learning rate |
| `NUM_GPUS` | `1` | Number of GPUs |
| `CHECKPOINT_DIR` | `/data1/jph/ckpts/vulrl_skyrl_test` | Checkpoint directory |
| `ROLLOUT_TIMEOUT` | `600` | Rollout timeout (seconds) |
| `POLL_INTERVAL` | `10` | Status polling interval (seconds) |
| `LOGGER` | `local` | Logging backend (local/wandb) |

### Hydra Configuration

The training uses Hydra for configuration management. Key parameters:

```yaml
# Data
data.train_data: ["path/to/train.parquet"]
data.val_data: null

# Model
trainer.policy.model.path: "/data1/jph/models/qwen2.5-1.5b"

# Training
trainer.epochs: 1
trainer.train_batch_size: 3
trainer.learning_rate: 1e-6

# Generator (VulRL-specific)
generator.worker_router_url: "http://localhost:5000"
generator.http_endpoint_host: "localhost"
generator.http_endpoint_port: 30000
generator.rollout_timeout: 600
generator.poll_interval: 10
generator.max_turns: 10

# GPU
trainer.placement.policy_num_gpus_per_node: 1
trainer.placement.colocate_all: true
```

### Override Configuration

```bash
# Add overrides to run_vulrl_skyrl.sh call
bash run_vulrl_skyrl.sh \
    trainer.epochs=10 \
    trainer.train_batch_size=16 \
    generator.max_turns=20
```

---

## Monitoring

### During Training

**Terminal Output**:
```
============================================================
VulRL SkyRL Training Launcher
============================================================
Configuration:
  Model: /data1/jph/models/qwen2.5-1.5b
  Worker Router: http://localhost:5000
  LLM Endpoint: http://localhost:30000
  Training Data: /data1/jph/.../train.parquet
  Epochs: 1
  Batch Size: 3
============================================================

[EzVulRLGenerator] Initialized
  Worker Router: http://localhost:5000
  LLM Endpoint: http://localhost:30000
  LLM Model: qwen2.5-1.5b

[EzVulRLGenerator] Generating batch of 3 trajectories
[EzVulRLGenerator] Submitting rollout: CVE-2024-28752
[EzVulRLGenerator] Task ID: abc-123-def-456
[EzVulRLGenerator] Polling for completion...
[EzVulRLGenerator] Received result: reward=0.5, steps=5
[EzVulRLGenerator] Generated 3/3 valid trajectories

[Trainer] Epoch 1/1, Batch 1/1
[Trainer] Average reward: 0.45
[Trainer] Success rate: 33%
[Trainer] Policy loss: 0.123
```

### Worker Router Logs

```bash
# View Worker Router logs
cd /data1/jph/VulRL/worker_orchestrator
tail -f logs/worker_router.log

# Check worker status
curl http://localhost:5000/api/workers/status | jq
```

### Worker Unit Logs

```bash
# View auto-spawned worker logs
cd /data1/jph/VulRL/worker_orchestrator
tail -f logs/worker_auto_*.log
```

### Redis Monitoring

```bash
# Check queue length
redis-cli LLEN rollout:queue:worker_auto_abc123

# Check task status
redis-cli HGETALL task:abc-123-def-456

# List all workers
redis-cli SMEMBERS workers

# Check worker status
redis-cli HGETALL worker:worker_auto_abc123
```

### Metrics to Watch

- **Average Reward**: Should increase over epochs
- **Success Rate**: Percentage of successful exploits
- **Policy Loss**: Should decrease over time
- **Token Length**: Average trajectory length
- **Rollout Time**: Time per rollout (should stabilize)
- **Worker Utilization**: Idle vs busy workers

---

## Troubleshooting

### Issue: Training doesn't start

**Symptoms**: Script exits immediately or hangs

**Solutions**:
```bash
# 1. Check all services are running
curl http://localhost:5000/health       # Worker Router
curl http://localhost:30000/v1/models   # LLM Server
redis-cli ping                          # Redis

# 2. Check training data exists
ls -lh /data1/jph/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/train.parquet

# 3. Check model path
ls -lh /data1/jph/models/qwen2.5-1.5b/

# 4. Check Python environment
which python
python --version
python -c "import ray; print(ray.__version__)"

# 5. Check CUDA
nvidia-smi
echo $CUDA_VISIBLE_DEVICES
```

### Issue: "No available workers"

**Symptoms**: Tasks queue but never execute

**Solutions**:
```bash
# 1. Check Worker Router is spawning workers
curl http://localhost:5000/api/workers/status | jq

# 2. Manually start a worker for testing
cd /data1/jph/VulRL/worker_orchestrator
source venv/bin/activate
python worker_unit/main.py --worker-id test_worker_01

# 3. Check worker logs
tail -f logs/worker_auto_*.log

# 4. Check Redis queue
redis-cli KEYS "rollout:queue:*"
redis-cli LLEN rollout:queue:worker_auto_abc123
```

### Issue: Rollouts timeout

**Symptoms**: Status stuck on "running", then fails

**Solutions**:
```bash
# 1. Increase timeout
export ROLLOUT_TIMEOUT=1200  # 20 minutes
bash run_vulrl_skyrl.sh

# 2. Check Docker is responding
docker ps
docker compose version

# 3. Check LLM server is responding
curl -X POST http://localhost:30000/v1/completions \
    -H "Content-Type: application/json" \
    -d '{"model":"qwen2.5-1.5b","prompt":"Hello","max_tokens":10}'

# 4. Check worker unit logs for errors
tail -100 logs/worker_auto_*.log | grep -i error
```

### Issue: Low reward / Poor performance

**Symptoms**: Rewards stay near 0, success rate is 0%

**Solutions**:
```bash
# 1. Check Vulhub paths are correct and accessible
ls -ld /data1/jph/vulhub/apache-cxf/CVE-2024-28752/
ls /data1/jph/vulhub/apache-cxf/CVE-2024-28752/docker-compose.yml

# 2. Test a single rollout manually
cd /data1/jph/VulRL/worker_orchestrator
bash test/ez_generator/test_simple.sh

# 3. Check LLM is generating reasonable commands
# (not just natural language)
tail -100 logs/worker_auto_*.log | grep -A 5 "LLM Response"

# 4. Adjust prompt in training data
# - Be more specific
# - Include examples of desired commands
# - Add constraints (e.g., "output ONLY bash commands")
```

### Issue: Out of memory

**Symptoms**: CUDA OOM errors, worker crashes

**Solutions**:
```bash
# 1. Reduce batch size
export TRAIN_BATCH_SIZE=1
bash run_vulrl_skyrl.sh

# 2. Reduce GPU memory utilization
# Edit run_vulrl_skyrl.sh:
# generator.gpu_memory_utilization=0.4  # from 0.8

# 3. Reduce max model length
# Edit run_vulrl_skyrl.sh:
# +generator.engine_init_kwargs.max_model_len=2048  # from 4096

# 4. Use smaller model
export MODEL_PATH="/path/to/smaller/model"
```

### Issue: Code changes not taking effect

**Symptoms**: Modified code doesn't run

**Solution**:
```bash
# The script syncs code on each run, but check:
ls -lt /data1/jph/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl_v2/

# If stale, manually sync:
rm -rf /data1/jph/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl_v2/*
cp -r /data1/jph/VulRL/worker_orchestrator/ez_generator/* \
      /data1/jph/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl_v2/
```

---

## Advanced Topics

### Custom Reward Function

Edit `worker_unit/reward/reward_calculator.py`:

```python
def calculate_reward(trajectory, env_info):
    """
    Custom reward calculation.
    
    Returns:
        float: Reward in range [0, 1]
    """
    # Example: Reward based on steps to success
    if env_info.get("exploit_successful"):
        steps_taken = len(trajectory)
        return 1.0 / (steps_taken + 1)  # Fewer steps = higher reward
    return 0.0
```

### Multi-GPU Training

```bash
# Edit run_vulrl_skyrl.sh
export NUM_GPUS=4

# Also update in script:
trainer.placement.policy_num_gpus_per_node=4
generator.num_inference_engines=4
generator.inference_engine_tensor_parallel_size=1
```

### WandB Integration

```bash
# Set WandB API key
export WANDB_API_KEY="your-api-key-here"
export LOGGER="wandb"
export WANDB_MODE="online"  # Remove "disabled"

# Run training
bash run_vulrl_skyrl.sh
```

### Resume from Checkpoint

```bash
# Set resume mode in run_vulrl_skyrl.sh:
trainer.resume_mode=latest  # or specific checkpoint path

# Checkpoints are saved to: $CHECKPOINT_DIR/
ls -lh /data1/jph/ckpts/vulrl_skyrl_test/
```

---

## Performance Tuning

### Batch Size vs Throughput

```
Batch Size 1:  ~120s per batch (3 rollouts sequential)
Batch Size 3:  ~120s per batch (3 rollouts parallel)  ← 3x speedup!
Batch Size 8:  ~150s per batch (8 rollouts parallel)  ← 6.4x speedup!
```

**Recommendation**: Set `TRAIN_BATCH_SIZE` to match your worker capacity.

### Worker Scaling

```bash
# Auto-scaling is enabled by default
# Workers spawn when no idle workers available
# Max workers: Unlimited (but limited by system resources)

# To pre-spawn workers:
for i in {1..8}; do
    python worker_unit/main.py --worker-id "worker_$i" &
done
```

### Polling Interval

```bash
# Lower = more responsive, higher CPU usage
export POLL_INTERVAL=5   # Check every 5 seconds

# Higher = less responsive, lower CPU usage
export POLL_INTERVAL=30  # Check every 30 seconds
```

---

## Next Steps

1. **Validate Setup**: Run `test_simple.sh` to verify Worker Router + Worker Units
2. **Create Real Data**: Convert your CVE dataset to Parquet format
3. **Tune Hyperparameters**: Start with small batch size, increase gradually
4. **Monitor Training**: Watch rewards and success rate
5. **Scale Up**: Add more workers, increase batch size
6. **Evaluate**: Test trained model on held-out CVEs

---

## Support

- **Documentation**: See `COMMUNICATION_FLOW.md` for detailed timing diagrams
- **Testing**: See `test/ez_generator/SIMPLIFIED_TEST_README.md`
- **Architecture**: See `ARCHITECTURE_DIAGRAM.md`

For issues, check logs:
- Worker Router: `logs/worker_router.log`
- Worker Units: `logs/worker_auto_*.log`
- SkyRL: `outputs/` (in SkyRL directory)
