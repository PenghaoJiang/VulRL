# VulRL Inside SkyRL - Training Setup

This directory contains a minimal, self-contained setup for training VulRL security exploitation agents using SkyRL.

## Directory Structure

```
vulrl_inside_skyrl/
├── run_training.sh          # Main launcher (checks deps, builds Docker, runs training)
├── main_training.py         # SkyRL entry point (registers SecurityEnv)
└── vulrl/                   # VulRL core modules (copied from infra_v4)
    ├── docker/              # Docker adapters for CVE-bench, Vulhub, Xbow
    │   ├── base/           # Base adapter classes
    │   └── adapters/       # Task-specific adapters
    ├── env/                # SecurityEnv (Gymnasium-compliant)
    └── reward/             # Reward calculation system
```

## Quick Start

### 1. Prerequisites

Ensure you're in WSL2 with:
- SkyRL installed at `~/SkyRL/skyrl-train`
- Docker installed and running
- Python 3.12
- CUDA-enabled GPU

### 2. Navigate to Directory

```bash
cd ~/SkyRL/skyrl-train/vulrl_inside_skyrl
```

Or from Windows mount:
```bash
cd /mnt/e/git_fork_folder/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl
```

### 3. Run Training

```bash
bash run_training.sh
```

This will:
- Check all prerequisites (Python, Docker, Ray)
- Build the `cve-attacker:latest` Docker image if needed
- Create minimal test data (2 CVE tasks)
- Launch SkyRL training with MINIMAL configuration (1 epoch, 10 turns)

## Configuration

The training is configured for **quick workflow testing** with minimal resources:

| Parameter | Value | Note |
|-----------|-------|------|
| **Model** | `/mnt/e/models/qwen2.5-1.5b` | Auto-downloads if not found |
| **Epochs** | 1 | Just for testing workflow |
| **Batch Size** | 1 | Minimal memory usage |
| **Max Turns** | 10 | Reduced from 30 for speed |
| **Rollouts** | 2 | 2 rollouts per task |
| **GPU Memory** | 0.5 (50%) | Safe for 8GB GPU |
| **LoRA Rank** | 8 | Small for faster training |

### Customizing Configuration

Edit variables at the top of `run_training.sh`:

```bash
# Example: Use HuggingFace auto-download instead of local model
export MODEL_NAME="Qwen/Qwen2.5-1.5B-Instruct"
export MODEL_PATH=""  # Empty to force HF download

# Example: Train for more epochs with larger batch
export EPOCHS=5
export TRAIN_BATCH_SIZE=4
export MAX_TURNS=30

# Then run
bash run_training.sh
```

## Model Path Configuration

The script supports multiple model sources:

1. **Local model** (if exists):
   ```bash
   MODEL_PATH=/mnt/e/models/qwen2.5-1.5b
   ```

2. **HuggingFace auto-download** (fallback):
   ```bash
   MODEL_NAME=Qwen/Qwen2.5-1.5B-Instruct
   ```

3. **Cache location** (auto-download target):
   ```bash
   ~/.cache/huggingface/hub/
   ```

## Training Data

By default, the script creates minimal test data (`test_data.parquet`) with 2 dummy CVE tasks.

To use real data:
```bash
# Set path to your prepared data
export TRAIN_DATA=/path/to/your/train.parquet
bash run_training.sh
```

Data format (Parquet):
```python
{
    "task_id": "CVE-2024-XXXX",
    "task_type": "cvebench",  # or "vulhub", "xbow"
    "cve_id": "CVE-2024-XXXX",
    "prompt": "Exploitation task description...",
    "target_info": {"service": "...", "port": 8080}
}
```

## Outputs

### Checkpoints
```bash
~/checkpoints/vulrl_test/
├── checkpoint_step_100/
├── checkpoint_step_200/
└── final/
```

### Logs
- **Console**: Training progress, loss, rewards
- **TensorBoard** (optional):
  ```bash
  tensorboard --logdir ~/checkpoints/vulrl_test
  ```

## Expected Output

```
============================================================
VulRL Security Training Launcher
============================================================

Checking prerequisites...

✓ Python: Python 3.12.x
✓ Docker: Docker version xx.xx.x
✓ Docker daemon: running
✓ Model: /mnt/e/models/qwen2.5-1.5b (local)

Checking Docker attacker image...

✓ Attacker image exists: cve-attacker:latest

Preparing training data...

✓ Training data ready: ./test_data.parquet

Setting up environment...

✓ Checkpoint directory: /home/user/checkpoints/vulrl_test
✓ PYTHONPATH: /path/to/vulrl_inside_skyrl

============================================================
Launching Training
============================================================

Configuration:
  Model: /mnt/e/models/qwen2.5-1.5b
  Data: ./test_data.parquet
  Epochs: 1
  Batch Size: 1
  Max Turns: 10
  Checkpoint: /home/user/checkpoints/vulrl_test

============================================================

[Training output...]
```

## Troubleshooting

### Error: "Docker daemon not running"
```bash
sudo systemctl start docker
```

### Error: "Model not found"
- Check if model exists at specified path
- Or let it auto-download from HuggingFace

### Error: "No module named 'vulrl'"
- Make sure you're running from `vulrl_inside_skyrl/` directory
- Check that PYTHONPATH includes current directory

### Error: "CUDA out of memory"
Reduce GPU memory usage:
```bash
export TRAIN_BATCH_SIZE=1
export GPU_MEMORY_UTILIZATION=0.4  # Edit in run_training.sh
```

### Error: "Ray connection failed"
```bash
# Kill existing Ray processes
ray stop
# Re-run training
bash run_training.sh
```

## Integration with infra_v4

This setup uses modules copied from `infra_v4/src/vulrl/`:
- **Docker adapters**: CVE-bench, Vulhub, Xbow (unchanged)
- **SecurityEnv**: Gymnasium-compliant environment
- **Reward system**: Task-specific reward calculation

To update from infra_v4:
```bash
# From VulRL root
rsync -av infra_v4/src/vulrl/docker/ SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/docker/
rsync -av infra_v4/src/vulrl/env/ SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/env/
rsync -av infra_v4/src/vulrl/reward/ SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/reward/
```

## Next Steps

1. **Test the workflow**: Run with minimal config (default)
2. **Verify outputs**: Check checkpoints and logs
3. **Scale up**: Increase epochs, batch size, max_turns
4. **Add real data**: Prepare CVE-bench/Vulhub/Xbow datasets
5. **Monitor training**: Use TensorBoard or WandB

## References

- **SkyRL**: https://github.com/NovaSkyAI/SkyRL
- **VulRL infra_v4**: `E:\git_fork_folder\VulRL\infra_v4\`
- **Qwen Model**: https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct
