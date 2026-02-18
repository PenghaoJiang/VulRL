# VulRL Inside SkyRL - Training Setup

This directory contains a minimal, self-contained setup for training VulRL security exploitation agents using SkyRL.

## Directory Structure

```
vulrl_inside_skyrl/
├── run_training.sh          # Main launcher (checks deps, builds Docker, runs training)
├── main_training.py         # SkyRL entry point (registers SecurityEnv)
└── vulrl/                   # VulRL core modules
    ├── docker/              # Docker adapters for CVE-bench, Vulhub, Xbow
    │   ├── base/           # Base adapter classes (StandardAction, StandardObservation)
    │   └── adapters/       # Task-specific adapters (VulhubAdapter, etc.)
    ├── env/                # SecurityEnv (Gymnasium-compliant)
    └── reward/             # Reward calculation system (BLEU-based)
        ├── reward_router.py        # Routes to task-specific implementations
        └── task_specific/
            ├── vulhub_reward.py    # BLEU-based reward (implemented)
            ├── cvebench_reward.py  # Placeholder
            └── xbow_reward.py      # Placeholder
```

## Reward System

### Overview

VulhubReward 使用修改版 BLEU 分数衡量 Agent 的漏洞利用轨迹与 ground truth PoC 脚本之间的相似度。

```
Agent trajectory (bash/http commands)
        ↓ 提取 action，拼接为文本
        ↓ tokenize
        hypothesis tokens
              │
              ├──→ BLEU-2 ──→ linear_map ──→ score_2 ─┐
              │                                        ├──→ 0.7×score_2 + 0.3×score_4 = reward
              └──→ BLEU-4 ──→ linear_map ──→ score_4 ─┘
```

### Computation Steps

1. **加载 Ground Truth**: 初始化时从 `train.parquet` 加载经 Docker 验证的 PoC 脚本（`poc_script` 字段），建立 `task_id → poc_script` 查找字典
2. **提取 Action**: 从 trajectory 中只提取 Agent 执行的命令（bash command / http request），不提取 observation
3. **Tokenize**: 统一小写，按 `[a-z0-9_.%-]+` 正则分词，过滤单字符噪声。自然地在 `://`、`:`、`/`、`{}`、`()` 等处断开，保留路径片段、端口号、payload 关键词
4. **计算 BLEU-2 和 BLEU-4**: 修改版 BLEU（无 Brevity Penalty），只计算 clipped n-gram precision 的几何平均
5. **线性映射**: 各自独立映射到 [0, 1]，低于 baseline 视为噪声返回 0
6. **加权合并**: `reward = 0.7 × mapped_BLEU2 + 0.3 × mapped_BLEU4`

### Why No Brevity Penalty

标准 BLEU 的 Brevity Penalty 惩罚比 reference 短的 hypothesis。但在本场景中：
- Hypothesis 是几条 bash 命令（~28 tokens）
- Reference 是完整 Python 脚本（~60 tokens），其中 72% 是 Python 模板代码（import、argparse、if \_\_name\_\_）

长度差异是格式结构性的，不反映 Agent 质量。保留 BP 会把精确攻击的 reward 从 0.78 压到 0.19。

### BLEU-2 vs BLEU-4

| 指标 | 衡量内容 | 信号特点 |
|------|---------|---------|
| BLEU-2 | 关键 token 及局部搭配（如 `cgi-bin`+`.%2e`） | 稳定，训练初期提供方向性梯度 |
| BLEU-4 | 连续 4-gram 匹配（如 `cgi-bin`+`.%2e`+`.%2e`+`bin`） | 稀疏，精确命中攻击路径时才出现 |

权重 0.7/0.3 偏向 BLEU-2，因为训练初期 Agent 随机探索时 BLEU-4 几乎为零，BLEU-2 能更早提供引导信号。

### Hyperparameters

| 参数 | 值 | 说明 |
|------|---|------|
| `BLEU2_BASELINE` | 0.03 | BLEU-2 噪声阈值 |
| `BLEU2_CAP` | 0.30 | BLEU-2 满分阈值 |
| `BLEU4_BASELINE` | 0.01 | BLEU-4 噪声阈值 |
| `BLEU4_CAP` | 0.20 | BLEU-4 满分阈值 |
| `WEIGHT_BLEU2` | 0.7 | BLEU-2 权重 |
| `WEIGHT_BLEU4` | 0.3 | BLEU-4 权重 |

以上为初始预估值，需跑真实 sample 后根据实际分布校准。

### Reward Examples

| Agent 行为 | BLEU-2 | BLEU-4 | Reward |
|-----------|--------|--------|--------|
| 精确命中攻击路径和 payload | 0.2440 | 0.1531 | **0.78** |
| 找对端口但路径错误 | 0.0000 | 0.0000 | **0.00** |
| 完全随机操作（ls, whoami） | 0.0000 | 0.0000 | **0.00** |

### Configuration

VulhubReward 通过 SecurityEnv 的 config 接收配置：

```python
config = {
    'task_type': 'vulhub',
    'task_id': 'apache/CVE-2021-41773',
    'dataset_path': '/path/to/train.parquet',  # Ground truth PoC 数据
    ...
}
```

如果未指定 `dataset_path`，会自动搜索以下默认路径：
- `~/data/cve_vulhub/train.parquet`
- `/data1/jph/VulRL/data/cve_vulhub/train.parquet`

### Call Chain

```
SkyRL PPO Training Loop
  → SecurityEnv.step()
    → episode done?
      → RewardRouter.compute_reward(trajectory, task_id)
        → VulhubReward.compute(trajectory, task_id)
          → extract actions → tokenize → BLEU-2/4 → linear map → weighted combine
          → return reward ∈ [0, 1]
```

## Quick Start

### 1. Prerequisites

- SkyRL installed at `~/SkyRL/skyrl-train`
- Docker installed and running
- Python 3.12
- CUDA-enabled GPU

### 2. Navigate to Directory

```bash
cd ~/SkyRL/skyrl-train/vulrl_inside_skyrl
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

## References

- **SkyRL**: https://github.com/NovaSkyAI/SkyRL
- **Qwen Model**: https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct
