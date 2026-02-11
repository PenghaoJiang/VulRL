# VulRL v4 - Infrastructure

Pragmatic, production-ready infrastructure for parallel RL training on vulnerability exploitation tasks.

## Quick Start

### Installation

```bash
cd infra_v4
pip install -e .
```

### Training

```bash
# Train on CVE-bench tasks
python rl_launcher.py \
    --task-type cvebench \
    --tasks-file tasks_cvebench.json \
    --base-model Qwen/Qwen2.5-3B-Instruct \
    --checkpoint-dir ./checkpoints \
    --max-episodes 100

# Train on Vulhub tasks
python rl_launcher.py \
    --task-type vulhub \
    --tasks-file tasks_vulhub.json \
    --max-episodes 100

# Train on specific tasks
python rl_launcher.py \
    --task-type cvebench \
    --task-ids "CVE-2024-2624,CVE-2024-2771" \
    --max-episodes 50
```

### Testing

```bash
# Test on single task
python test_trained_model.py \
    --checkpoint ./checkpoints/global_step_1000 \
    --task-type cvebench \
    --task-id CVE-2024-2624

# Batch testing
python test_trained_model.py \
    --checkpoint ./checkpoints/global_step_1000 \
    --tasks-file tasks_cvebench.json \
    --output results.json
```

## Architecture

```
infra_v4/
├── rl_launcher.py              # Training entry point
├── test_trained_model.py       # Testing entry point
├── src/vulrl/
│   ├── parallel/               # Parallel execution
│   │   ├── process_coordinator.py
│   │   ├── progress_monitor.py
│   │   └── ray_config.py
│   ├── skyrl/                  # SkyRL integration
│   │   └── skyrl_wrapper.py
│   ├── env/                    # Environments
│   │   ├── security_env.py
│   │   └── env_registry.py
│   ├── docker/                 # Adapters (copied from infra/)
│   │   ├── base/
│   │   └── adapters/
│   ├── reward/                 # Reward system
│   │   └── task_specific/
│   └── model/                  # Model management
│       ├── checkpoint_manager.py
│       └── lora_loader.py
└── tasks_*.json                # Task lists
```

## Key Features

### 1. Parallel Training
- Train on multiple CVEs simultaneously using `ProcessPoolExecutor`
- Each CVE gets its own process
- SkyRL uses Ray internally for trajectory collection

### 2. Real-time Progress Monitoring
- Multiple progress bars (one per CVE)
- Shows episode number and step progress
- Clean terminal display with `tqdm`

### 3. Self-Contained Adapters
- Copied unchanged from infra/infra_v2
- No abstraction layers - all Docker logic inside adapters
- Proven, stable code

### 4. Flexible Testing
- Works with CVE-bench, Vulhub, and Xbow
- No Inspect AI dependency
- Batch testing support

### 5. Task-Specific Rewards
- Router-based reward system
- Separate implementations for each task type
- Easy to extend

## Design Philosophy

**Pragmatic over Perfect:**
- Focus on NEW features (parallel execution, SkyRL integration)
- COPY existing adapters (proven, working code)
- SKIP unnecessary abstraction layers

**Value = Parallel Training + SkyRL Integration**

## Progress Bar Example

```
Training 4 CVEs in parallel...

[CVE-2024-2624    ] Ep 12/100 | Step 23/30 (76%) |████████████░░░░| 76/100
[CVE-2024-2771    ] Ep  8/100 | Step 10/30 (33%) |█████░░░░░░░░░░░| 33/100
[CVE-2024-3094    ] Ep 15/100 | Step 28/30 (93%) |██████████████░░| 93/100
[jenkins/CVE-18861] Ep  3/100 | Step  5/30 (17%) |███░░░░░░░░░░░░░| 17/100

Overall: 4 tasks running | Avg progress: 54.8%
```

## TODO: Implement Reward Logic

Currently all reward functions return 0. Implement in:
- `src/vulrl/reward/task_specific/cvebench_reward.py`
- `src/vulrl/reward/task_specific/vulhub_reward.py`
- `src/vulrl/reward/task_specific/xbow_reward.py`

## Dependencies

See `pyproject.toml` for full list. Main dependencies:
- `tqdm` - Progress bars
- `gymnasium` - RL environment interface
- `docker` - Container management
- `ray` - Distributed computing (for SkyRL)
- `torch` - Deep learning
- `transformers` - LLM models
- `peft` - LoRA fine-tuning

## Differences from infra_v3

| Feature | infra_v3 | infra_v4 |
|---------|----------|----------|
| Docker abstraction | ✅ docker_manager.py | ❌ Self-contained adapters |
| Adapters | Refactored to use manager | Copied unchanged |
| Parallel module | In entry point | Separate module |
| SkyRL integration | Implicit | Explicit wrapper |
| Progress bars | Basic | Multi-task with tqdm |
| Philosophy | Clean architecture | Ship fast |

**infra_v4 is simpler because it's more pragmatic.**
