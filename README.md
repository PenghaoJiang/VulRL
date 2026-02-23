
# VulRL - Unified Security RL Training System

基于 SkyRL 框架和 LoRA 微调的**统一安全强化学习训练系统**。

## 🌟 核心特性

- ✅ **统一环境接口**：支持 Vulhub + CTF (CVE-bench) 混合训练
- ✅ **跨环境能力迁移**：Agent 学习通用漏洞利用能力，而非特定环境技巧
- ✅ **标准化接口**：遵循 Gymnasium 规范，易于扩展新数据源
- ✅ **BLEU-based 奖励机制**：对比 Agent 命令序列与 Ground Truth PoC 脚本的 BLEU 相似度
- ✅ **自动 PoC 生成**：使用 GPT-4o 从 README 自动生成可执行 Python PoC
- ✅ **向后兼容**：现有训练代码无需修改

## 📊 支持的数据源

| 数据源 | 类型 | 环境数量 | 特点 |
|--------|------|---------|------|
| **Vulhub** | CVE 漏洞环境 | 700+ | 真实漏洞复现，Docker Compose 启动 |
| **CVE-bench** | CTF 挑战 | 40+ | 关键严重性 CVE，多种攻击类型 |
| **Custom** | 自定义环境 | 可扩展 | 通过适配器插件化添加 |

## 目录结构

```
VulRL/
├── README.md                          # 本文档
├── dataset/                           # 数据集模块
│   ├── vulhub_dataset_builder.py     # Vulhub 数据集构建器
│   ├── dataset_converter.py          # 统一格式转换工具 (支持 skyrl/ctf-skyrl 子命令)
│   └── cve_vulhub/                   # 生成的训练数据
│       └── train.parquet             # Vulhub 训练数据集
├── infra/                             # 训练和测试基础设施
│   ├── env_types.py                  # 标准化数据结构 (NEW)
│   ├── env_adapter.py                # 适配器抽象基类 (NEW)
│   ├── vulhub_adapter.py             # Vulhub 适配器 (NEW)
│   ├── ctf_adapter.py                # CTF 适配器 (NEW)
│   ├── security_env.py               # 统一环境 (NEW)
│   ├── cve_exploit_env.py            # 原 RL 环境（保留奖励组件）
│   ├── main_training.py              # SkyRL 训练入口（已更新）
│   ├── train_launcher.py             # 训练启动器（已更新）
│   ├── test_launcher.py              # CVE-bench 测试启动器
│   ├── lora_model_provider.py        # Inspect AI 模型提供者
│   ├── _registry.py                  # 模型注册
│   ├── UNIFIED_ENV_GUIDE.md          # 统一环境详细指南 (NEW)
│   ├── test_unified_env.py           # 测试脚本 (NEW)
│   └── pyproject.toml                # 项目配置
├── benchmark/                         # 基准测试
│   ├── cve-bench/                    # CVE-bench 仓库
│   └── vulhub/                       # Vulhub 仓库
└── eval_results/                     # 测试结果目录
```

## 系统架构

### 统一环境架构（v2.0 新特性）

```
┌─────────────────────────────────────────────────────────────┐
│                 Training Pipeline                            │
├─────────────────────────────────────────────────────────────┤
│  train_launcher.py  →  main_training.py  →  SkyRL Framework │
│         ↓                    ↓                    ↓          │
│   配置参数生成           Ray 初始化          GRPO 训练循环    │
│         ↓                    ↓                    ↓          │
│   启动训练命令         环境注册(NEW)        LoRA 微调         │
├─────────────────────────────────────────────────────────────┤
│              Unified Environment Layer (NEW)                 │
├─────────────────────────────────────────────────────────────┤
│  SecurityEnv (统一环境接口，遵循 Gymnasium 规范)              │
│  ├── reset() -> (observation, info)                         │
│  └── step(action) -> (obs, reward, terminated, truncated)   │
│                      ↓                                       │
│            ┌─────────┴─────────┐                            │
│            ↓                   ↓                             │
│    VulhubAdapter          CTFAdapter                         │
│    (Vulhub 数据源)        (CVE-bench/CTF)                    │
│            ↓                   ↓                             │
│    返回值标准化           返回值标准化                        │
├─────────────────────────────────────────────────────────────┤
│              Bottom Layer Implementations                    │
├─────────────────────────────────────────────────────────────┤
│  Docker Compose (Vulhub)  │  Dockerfile/Compose (CTF)       │
│  Vulhub Container         │  CTF Container                   │
│       ↕                   │       ↕                          │
│  Attacker Container       │  Attacker Container              │
├─────────────────────────────────────────────────────────────┤
│                  Reward Mechanism (BLEU-based)              │
├─────────────────────────────────────────────────────────────┤
│  RewardRouter → VulhubReward (BLEU)                         │
│    BLEU(Agent命令序列, GT PoC脚本) → reward ∈ [0, 1]        │
└─────────────────────────────────────────────────────────────┘
```

### 关键改进

**统一标准**：
- 所有环境（Vulhub/CTF）返回相同的标准化数据结构
- Agent 只与标准接口交互，不感知底层差异

**能力迁移**：
- 在 Vulhub 和 CTF 之间混合训练
- Agent 学习通用的漏洞利用技能

**易于扩展**：
- 新增数据源只需实现一个适配器类
- 插件化架构，无需修改核心代码

## 前置要求

### 1. 系统要求
- Linux 服务器（推荐 Ubuntu 20.04+）
- NVIDIA GPU（至少 48GB 显存，推荐 96GB）
- Docker 和 Docker Compose
- Python 3.10+

### 2. 软件依赖

```bash
# 安装 uv（Python 包管理器）
curl -LsSf https://astral.sh/uv/install.sh | sh

# 克隆 SkyRL
cd ~
git clone https://github.com/NovaSkyAI/SkyRL.git

# 克隆 Vulhub
git clone https://github.com/vulhub/vulhub.git

# 安装 Tesseract OCR（用于图片文字提取）
# macOS
brew install tesseract

# Ubuntu/Debian
sudo apt-get install tesseract-ocr

# 安装 Python OCR 依赖
pip install pytesseract Pillow
```

### 3. 环境变量

```bash
# OpenAI API Key（用于 LLM-as-Judge）也可以换成其他的api(修改对应的依赖和代码使用就行）
export OPENAI_API_KEY="your-openai-api-key"
```

## 快速开始

### 📖 完整文档

- **统一环境详细指南**：[infra/UNIFIED_ENV_GUIDE.md](infra/UNIFIED_ENV_GUIDE.md)
  - API 参考、混合训练、故障排除、扩展指南

### Step 0: 数据构建与转换

完整的数据流水线包含两步：**构建 24 列原始数据** → **转换为 SkyRL 7 列统一格式**。

#### 方式 A：从零构建（推荐）

适用于首次使用或需要处理新 CVE 的场景。

```bash
cd ~/PycharmProjects/SecurityRL/VulRL/dataset

# 第 1 步：用 builder 生成 24 列 parquet（需要 OpenAI API Key）
python vulhub_dataset_builder.py \
    --vulhub_path ~/vulhub \
    --output_dir ~/data/cve_vulhub_raw

# 第 2 步：转换为 SecurityEnv 7 列 SkyRL 格式
python dataset_converter.py skyrl \
    --input ~/data/cve_vulhub_raw/train.parquet \
    --output ~/data/cve_vulhub_skyrl/train.parquet \
    --vulhub-base-dir ~/vulhub
```

只处理指定 CVE（测试用）：
```bash
# 创建只包含目标 CVE 的 vulhub 子集
mkdir -p /tmp/vulhub_subset/h2database
ln -sf ~/vulhub/h2database/CVE-2022-23221 /tmp/vulhub_subset/h2database/
ln -sf ~/vulhub/h2database/CVE-2018-10054 /tmp/vulhub_subset/h2database/

# 用子集跑 builder
python vulhub_dataset_builder.py \
    --vulhub_path /tmp/vulhub_subset \
    --output_dir ~/data/cve_h2_test

# 转换
python dataset_converter.py skyrl \
    --input ~/data/cve_h2_test/train.parquet \
    --output ~/data/cve_h2_test_skyrl/train.parquet
```

#### 方式 B：转换为 JSON 配置（旧方式）

```bash
# Vulhub → JSON
python dataset_converter.py vulhub \
    --input ~/data/cve_vulhub/train.parquet \
    --output ~/unified_tasks/vulhub \
    --format json

# CVE-bench → JSON
python dataset_converter.py cvebench \
    --input ~/benchmark/cve-bench \
    --output ~/unified_tasks/ctf \
    --variant zero_day
```

#### 方式 C：CTF → SkyRL 格式

```bash
python dataset_converter.py ctf-skyrl \
    --input ~/benchmark/cve-bench \
    --output ~/data/ctf_skyrl/train.parquet \
    --variant zero_day
```

#### 验证转换结果

```bash
python -c "
import pandas as pd, json
df = pd.read_parquet('~/data/cve_vulhub_skyrl/train.parquet')
print(f'列: {list(df.columns)}')
print(f'行数: {len(df)}')
row = df.iloc[0]
print(f'env_class: {row[\"env_class\"]}')
config = json.loads(row['env_config'])
print(f'task_type: {config[\"task_type\"]}')
print(f'target: {config[\"target_host\"]}:{config[\"target_port\"]}')
poc = json.loads(row['poc_info'])
print(f'poc_info keys: {list(poc.keys())}')
"
```

#### SkyRL 7 列输出 Schema

| 列名 | 类型 | 说明 |
|------|------|------|
| `prompt` | str (JSON) | system + user message（不泄露漏洞类型） |
| `env_class` | str | 固定 `"security_env.SecurityEnv"` |
| `env_config` | str (JSON) | StandardEnvConfig 格式（含 task_id/target/evaluation_config/poc_info/backend_config） |
| `poc_info` | str (JSON) | 独立列，SecurityEnv._parse_config() 单独读取，用于 Reward 计算 |
| `tools` | str (JSON) | bash + http_request 工具定义 |
| `task_id` | str | CVE 编号 |
| `metadata` | str (JSON) | cve_id, source, vulhub_path 等元信息 |

**数据流**：
```
SkyRL PromptDataset.__getitem__()
  → pop "prompt" 和 "env_class"
  → 剩余 5 列打包为 extras dict
  → SecurityEnv.__init__(extras=extras)
  → SecurityEnv._parse_config():
      extras["env_config"] → JSON parse → StandardEnvConfig
      extras["poc_info"]   → JSON parse → 用于 Reward 计算
```

> **注意**：旧的 6 列格式（CVEExploitEnv）缺少 poc_info 等关键字段，无法用于 SecurityEnv。必须从 24 列原始数据转换。

### Step 1: 构建 Vulhub 数据集

数据集构建器 v2.0 会自动：
1. 解析 README 文件（提取代码块、图片）
2. 使用 OCR 提取图片中的文字
3. 使用 GPT-4o 分析漏洞信息
4. **生成完整可执行的 Python PoC 脚本**
5. 使用 LLM 验证 PoC 正确性（最多 3 次重试）

```bash
# 处理所有 CVE（需要 OpenAI API Key）
python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ./cve_vulhub

# 测试模式：只处理前 10 个 CVE
python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ./cve_vulhub --limit 10

# 使用更便宜的模型
python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ./cve_vulhub --model gpt-4o-mini
```

**参数说明：**
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--vulhub_path` | `~/vulhub` | Vulhub 仓库路径 |
| `--output_dir` | `~/data/cve_vulhub` | 输出数据集路径 |
| `--limit` | `None` | 限制处理的 CVE 数量（用于测试） |
| `--model` | `gpt-4o` | 使用的 OpenAI 模型 |
| `--api_key` | `$OPENAI_API_KEY` | OpenAI API Key |

### Step 2: 启动训练

#### 选项 A：仅 Vulhub 训练（传统方式）

```bash
export WANDB_API_KEY="your-wandb-key"
python infra/train_launcher.py
```

#### 选项 B：混合训练（推荐，利用统一环境 + SkyRL 格式）

确保已完成 Step 0 生成 SkyRL 7 列 parquet，然后修改 `train_launcher.py` 的数据路径配置：

```python
# 在 build_command() 方法中，指向 SkyRL 格式的 parquet
params = [
    # 使用 SecurityEnv 统一格式数据
    f"++data.train_data='{skyrl_data_dir}/train.parquet'",
    # 或混合 Vulhub 和 CTF 数据
    f"++data.train_data=['{vulhub_skyrl_dir}/train.parquet', '{ctf_skyrl_dir}/train.parquet']",
    # ...其他参数
]
```

然后启动训练：

```bash
export WANDB_API_KEY="your-wandb-key"
python infra/train_launcher.py
```

训练启动器会自动：
1. 检查前置条件（SkyRL、Vulhub、Docker、数据集）
2. 构建 attacker Docker 镜像
3. 复制必要文件到 SkyRL 目录
4. 使用统一环境（SecurityEnv）启动训练
5. Agent 在 Vulhub 和 CTF 环境之间切换学习

## 配置参数详解

### 训练配置 (`train_launcher.py`)

所有训练参数都在 `train_launcher.py` 的 `build_config()` 和 `build_command()` 方法中定义。

#### 基础配置 (`build_config` 方法，第 143-162 行)

```python
def build_config(self) -> dict:
    return {
        "model_path": "Qwen/Qwen2.5-3B-Instruct",  # 基础模型
        "train_data": str(self.data_dir / "train.parquet"),  # 训练数据
        "algorithm": "grpo",           # 算法：GRPO
        "advantage_estimator": "rloo", # 优势估计：RLOO
        "train_batch_size": 4,         # 批次大小
        "rollouts_per_task": 4,        # 每个任务的 rollout 数
        "learning_rate": 1e-6,         # 学习率
        "epochs": 20,                  # 训练轮数
        "checkpoint_dir": str(self.checkpoint_dir),  # checkpoint 保存路径
    }
```

#### 详细参数配置 (`build_command` 方法，第 164-234 行)

| 类别 | 参数 | 默认值 | 说明 | 代码位置 |
|------|------|--------|------|----------|
| **数据** | `data.train_data` | `./cve_vulhub/train.parquet` | 训练数据路径 | 第 176 行 |
| | `data.val_data` | `null` | 验证数据（已禁用） | 第 177 行 |
| **算法** | `trainer.algorithm.name` | `grpo` | 算法名称 | 第 180 行 |
| | `trainer.algorithm.advantage_estimator` | `rloo` | 优势估计方法 | 第 181 行 |
| | `trainer.algorithm.kl_coef` | `0.0` | KL 散度系数 | 第 182 行 |
| | `trainer.algorithm.entropy_coef` | `0.0` | 熵系数 | 第 183 行 |
| | `trainer.algorithm.normalize_advantage` | `False` | 是否归一化优势 | 第 184 行 |
| **批次** | `trainer.train_batch_size` | `4` | 训练批次大小 | 第 187 行 |
| | `trainer.policy_mini_batch_size` | `4` | 策略更新小批次 | 第 188 行 |
| | `trainer.rollout_batch_size` | `4` | rollout 批次大小 | 第 189 行 |
| | `trainer.rollouts_per_task` | `4` | 每任务 rollout 数 | 第 190 行 |
| **训练** | `trainer.learning_rate` | `1e-6` | 学习率 | 第 191 行 |
| | `trainer.epochs` | `20` | 训练轮数 | 第 192 行 |
| | `trainer.eval_interval` | `-1` | 评估间隔（-1 禁用） | 第 193 行 |
| | `trainer.save_interval` | `10` | checkpoint 保存间隔 | 第 197 行 |
| **模型** | `trainer.policy.model.path` | `Qwen/Qwen2.5-3B-Instruct` | 基础模型路径 | 第 200 行 |
| **LoRA** | `trainer.policy.model.lora.rank` | `16` | LoRA 秩 | 第 203 行 |
| | `trainer.policy.model.lora.alpha` | `32` | LoRA alpha | 第 204 行 |
| | `trainer.policy.model.lora.dropout` | `0.05` | LoRA dropout | 第 205 行 |
| | `trainer.policy.model.lora.target_modules` | `all-linear` | 目标模块 | 第 206 行 |
| **GPU** | `trainer.placement.colocate_all` | `true` | 所有组件共置 | 第 209 行 |
| | `trainer.placement.policy_num_gpus_per_node` | `1` | 策略 GPU 数 | 第 211 行 |
| | `generator.gpu_memory_utilization` | `0.5` | GPU 内存利用率 | 第 223 行 |
| | `generator.engine_init_kwargs.max_model_len` | `4096` | 最大模型长度 | 第 224 行 |
| **其他** | `dispatcher.strategy` | `async_pipeline` | 调度策略 | 第 227 行 |
| | `logging.backend` | `local` | 日志后端 | 第 230 行 |

### 环境配置

环境配置通过 `env_config` JSON 传入 SecurityEnv，包含以下字段：

| 参数 | 类型 | 说明 |
|------|------|------|
| `task_id` | `str` | CVE 编号（如 `CVE-2016-3088`） |
| `task_type` | `str` | 任务类型（`vulhub` / `ctf`） |
| `target_host` | `str` | 目标服务名 |
| `target_port` | `int` | 目标端口 |
| `max_steps` | `int` | 最大步数（默认 30） |
| `poc_info` | `Dict` | PoC 信息（用于 BLEU reward 计算） |
| `backend_config` | `Dict` | 后端配置（vulhub_path 等） |

### Ray 配置 (`main_training.py`)

| 参数 | 默认值 | 说明 | 代码位置 |
|------|--------|------|----------|
| `num_gpus` | `1` | GPU 数量 | 第 51 行 |
| `_temp_dir` | `~/ray_tmp` | Ray 临时目录 | 第 53 行 |
| `CUDA_VISIBLE_DEVICES` | `0` | 可见 GPU | 第 20 行 |

## 路径配置

### 默认路径 (`train_launcher.py` 第 20-26 行)

| 路径 | 默认值 | 说明 |
|------|--------|------|
| `skyrl_dir` | `~/SkyRL/skyrl-train` | SkyRL 安装目录 |
| `data_dir` | `./cve_vulhub` | 训练数据目录 |
| `checkpoint_dir` | `~/checkpoints/cve_agent` | Checkpoint 保存目录 |
| `vulhub_dir` | `~/vulhub` | Vulhub 仓库目录 |

## 可用工具

统一环境提供两个标准化工具供 Agent 使用，在所有环境类型（Vulhub/CTF）中保持一致：

### 1. bash
在攻击者容器内执行任意 bash 命令。

```json
{
  "tool": "bash",
  "arguments": {
    "command": "nmap -p 1-1000 target"
  }
}
```

**示例**：
```json
{"tool": "bash", "arguments": {"command": "curl -v http://target:80/"}}
{"tool": "bash", "arguments": {"command": "python3 -c 'import requests; print(requests.get(\"http://target\").text)'"}}
```

### 2. http_request
发送 HTTP 请求。

```json
{
  "tool": "http_request",
  "arguments": {
    "method": "POST",
    "url": "http://target/api",
    "headers": {"Content-Type": "application/json"},
    "json": {"key": "value"}
  }
}
```

**示例**：
```json
{"tool": "http_request", "arguments": {"method": "GET", "path": "/"}}
{"tool": "http_request", "arguments": {"method": "POST", "path": "/login", "json": {"user": "admin", "pass": "admin"}}}
```

### 工具特性

- ✅ **标准化接口**：所有环境使用相同的工具调用格式
- ✅ **自动路由**：工具调用自动路由到对应的适配器
- ✅ **容器内执行**：在隔离的 attacker 容器中安全执行
- ✅ **输出一致**：统一的输出格式（exit code + stdout + stderr）

## 奖励机制

### BLEU-based Reward（当前实现）

当前奖励系统使用 **BLEU 分数**衡量 Agent 执行的命令序列与 Ground Truth PoC 脚本之间的相似度。

**代码位置**：`SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/reward/`

#### 计算流程

```
Episode 结束
    ↓
从 trajectory 提取 Agent 的所有 bash/http 命令 → actions_text
    ↓
从 train.parquet 加载该 CVE 的 Ground Truth PoC 脚本 → ground_truth
    ↓
tokenize 两段文本（小写化，按空格和代码分隔符切分）
    ↓
计算 BLEU-2 和 BLEU-4（无 brevity penalty）
    ↓
线性映射 + 加权组合 → reward ∈ [0, 1]
```

#### 奖励公式

```python
# 1. 计算 BLEU 分数（无 brevity penalty）
bleu2 = BLEU(agent_tokens, poc_tokens, max_n=2)
bleu4 = BLEU(agent_tokens, poc_tokens, max_n=4)

# 2. 线性映射到 [0, 1]（过滤噪声，防止饱和）
score2 = linear_map(bleu2, baseline=0.03, cap=0.30)  # <0.03→0, >0.30→1
score4 = linear_map(bleu4, baseline=0.01, cap=0.20)  # <0.01→0, >0.20→1

# 3. 加权组合
reward = 0.7 * score2 + 0.3 * score4
```

#### 设计考量

| 设计决策 | 原因 |
|---------|------|
| 不用 brevity penalty | Agent 输出的是 bash 命令，PoC 是 Python 脚本，格式不同导致长度天然不同 |
| BLEU-2 权重 (0.7) > BLEU-4 (0.3) | bi-gram 在跨格式比较中更稳定，4-gram 匹配率天然很低 |
| baseline 阈值 | 过滤随机命令产生的噪声匹配 |
| cap 上限 | 避免高分饱和，保持梯度信号 |

#### Reward Router

系统通过 `RewardRouter` 按 `task_type` 路由到不同实现：

| task_type | 实现类 | 状态 |
|-----------|--------|------|
| `vulhub` | `VulhubReward` | BLEU-based，已实现 |
| `cvebench` | `CVEBenchReward` | Placeholder（返回 0.0） |
| `xbow` | `XbowReward` | Placeholder（返回 0.0） |

#### 调用链路

```python
SecurityEnv.step(action)
    ↓ episode 结束
RewardRouter.compute_reward(trajectory, task_id)
    ↓ task_type == "vulhub"
VulhubReward.compute(trajectory, task_id)
    ↓
BLEU(Agent 命令序列, GT PoC 脚本) → reward ∈ [0, 1]
```

> **注意**：`infra/cve_exploit_env.py` 和 `infra/security_env.py` 中仍保留旧的三层 LLM Judge 代码（StepJudge / TrajectoryJudge / LLM1Judge），但训练实际使用的是 `vulrl_inside_skyrl/` 下的新版 SecurityEnv + BLEU reward。旧代码仅作历史参考。

## 常见问题

### 1. 磁盘空间不足

```
OSError: [Errno 28] No space left on device
```

**解决方案**：清理 Ray 临时目录
```bash
ray stop
rm -rf ~/ray_tmp
rm -rf /tmp/ray*
```

### 2. GPU 内存不足

**解决方案**：调整 `gpu_memory_utilization`
```python
# train_launcher.py 第 223 行
"++generator.gpu_memory_utilization=0.3",  # 降低到 30%
```

### 3. Checkpoint 加载失败

如果修改了 LoRA 配置后无法加载旧 checkpoint：
```bash
rm -rf ~/checkpoints/cve_agent
```

### 4. Docker Compose 版本问题

系统会自动检测 `docker compose` 或 `docker-compose` 命令。

## 监控训练

训练过程会自动上传到 Weights & Biases：
- 项目：`skyrl`
- 查看地址：https://wandb.ai/your-username/skyrl

## 自定义训练

### 修改基础模型

```python
# train_launcher.py build_config() 方法
"model_path": "Qwen/Qwen2.5-7B-Instruct",  # 使用更大的模型
```

### 调整 LoRA 参数

```python
# train_launcher.py build_command() 方法
"++trainer.policy.model.lora.rank=32",     # 增加 LoRA 秩
"++trainer.policy.model.lora.alpha=64",    # 相应增加 alpha
```

### 增加训练步数

```python
# train_launcher.py build_config() 方法
"epochs": 50,  # 增加到 50 轮
```

### 调整 BLEU Reward 参数

```python
# vulrl_inside_skyrl/vulrl/reward/task_specific/vulhub_reward.py
BLEU2_BASELINE = 0.03   # BLEU-2 低于此值视为噪声，reward=0
BLEU2_CAP = 0.30         # BLEU-2 高于此值视为满分，reward=1
BLEU4_BASELINE = 0.01
BLEU4_CAP = 0.20
WEIGHT_BLEU2 = 0.7       # BLEU-2 权重
WEIGHT_BLEU4 = 0.3       # BLEU-4 权重
```

## 文件说明

### vulhub_dataset_builder.py (v2.0)

从 Vulhub 仓库解析 CVE 信息，**生成可执行的 Python PoC 脚本**，并输出训练数据集。

**核心特性**：
1. 全面理解 README（文本 + 代码块 + 图片 OCR）
2. 生成完整可执行的 Python PoC 脚本
3. LLM 逻辑验证确保 PoC 正确性（最多 3 次重试）
4. 以 PoC 为中心的数据集结构

**处理流程**：
```
VulhubScanner → ContentParser → PoCGenerator → PoCValidator → DatasetWriter
     ↓              ↓               ↓              ↓
  扫描CVE目录    解析README      生成Python脚本   LLM验证
                提取代码块                      (最多3次重试)
                OCR处理图片
```

**主要类**：
| 类名 | 功能 |
|------|------|
| `VulhubScanner` | 扫描 Vulhub 仓库中的有效 CVE 目录 |
| `ContentParser` | 解析 README（代码块、图片、链接） |
| `OCRProcessor` | 使用 pytesseract 提取图片文字 |
| `PoCGenerator` | 使用 GPT-4o 生成 Python PoC 脚本 |
| `PoCValidator` | 使用 LLM 验证 PoC 正确性 |
| `DatasetBuilder` | 编排整个流程，输出 parquet 数据集 |

**数据类**：
| 类名 | 功能 |
|------|------|
| `CodeBlock` | README 中的代码块（语言、内容、上下文） |
| `ImageContent` | 图片 OCR 内容和描述 |
| `ReadmeAnalysis` | README 综合分析结果 |
| `GeneratedPoC` | 生成的 PoC 脚本及元数据 |
| `VulhubEntry` | 完整的 Vulhub 条目（核心数据结构） |

**输出格式（train.parquet，共 24 个字段）**：
| 字段 | 类型 | 说明 |
|------|------|------|
| `cve_id` | str | CVE 编号 |
| `vulhub_path` | str | Vulhub 相对路径 |
| `vulnerability_type` | str | 漏洞类型（rce/sqli/ssti 等） |
| `service_name` | str | 服务名称 |
| `service_version` | str | 受影响版本 |
| `vulnerability_description` | str | 漏洞描述 |
| `primary_port` | int | 主要攻击端口 |
| `exposed_ports` | str | JSON 暴露端口列表 |
| `primary_service` | str | 主要服务名称 |
| **`poc_script`** | str | **生成的完整 Python PoC（核心字段）** |
| `poc_dependencies` | str | JSON 依赖列表 |
| `poc_execution_cmd` | str | PoC 执行命令 |
| `exploitation_steps` | str | JSON 利用步骤 |
| `success_indicators` | str | JSON 成功标志 |
| `readme_content` | str | README 原文 |
| `code_blocks` | str | JSON 代码块列表 |
| `image_ocr_content` | str | JSON OCR 结果 |
| `original_poc_files` | str | JSON 原有 PoC 文件 |
| `reference_links` | str | JSON 参考链接列表 |
| `validation_status` | str | validated/needs_review/failed |
| `validation_score` | float | 验证分数 (0.0-1.0) |
| `validation_notes` | str | 验证说明 |
| `generation_model` | str | 使用的 LLM 模型 |
| `generation_timestamp` | str | 生成时间 (ISO 格式) |

### dataset_converter.py

数据格式转换工具，支持多种输入输出格式。

**子命令**：

| 子命令 | 输入 | 输出 | 说明 |
|--------|------|------|------|
| `skyrl` | 24 列 Vulhub parquet | 7 列 SkyRL parquet | **推荐**，供 SecurityEnv 训练使用 |
| `ctf-skyrl` | CVE-bench 目录 | 7 列 SkyRL parquet | CTF 数据的 SkyRL 格式转换 |
| `vulhub` | 24 列 Vulhub parquet | JSON 配置文件 | 旧格式，逐 CVE 输出 JSON |
| `cvebench` | CVE-bench 目录 | JSON 配置文件 | 旧格式，逐 challenge 输出 JSON |
| `custom-ctf` | 自定义 CTF JSON | JSON 配置文件 | 自定义 CTF 格式转换 |

**skyrl 子命令参数**：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--input` | 必填 | 24 列 train.parquet 路径 |
| `--output` | 必填 | 输出 parquet 文件路径 |
| `--vulhub-base-dir` | `~/vulhub` | Vulhub 仓库根目录（用于扫描 ground-truth 图片） |

**主要类与方法**：

| 类 | 方法 | 说明 |
|----|------|------|
| `VulhubToUnifiedConverter` | `to_skyrl_parquet()` | 24 列 → 7 列 SkyRL parquet |
| `VulhubToUnifiedConverter` | `convert()` | 24 列 → JSON（旧方式） |
| `CTFToUnifiedConverter` | `ctf_to_skyrl_parquet()` | CVE-bench → 7 列 SkyRL parquet |
| `CTFToUnifiedConverter` | `convert_cvebench()` | CVE-bench → JSON（旧方式） |

### cve_exploit_env.py（旧版，仅作历史参考）

旧版 RL 环境实现，包含已弃用的三层 LLM Judge 奖励系统。

**主要类**（已弃用，不再用于训练）：
- `CVEExploitEnv`：旧版主环境类
- `LLM1Judge`：LLM 视觉判断器（已被 BLEU reward 替代）
- `StepJudge`：步骤判断器（已被 BLEU reward 替代）
- `TrajectoryJudge`：轨迹判断器（已被 BLEU reward 替代）
- `ScreenshotGenerator`：截图生成器（已弃用）

> 当前训练使用 `vulrl_inside_skyrl/vulrl/env/security_env.py` + `VulhubReward`（BLEU-based）。

### main_training.py

SkyRL 训练入口点。

**功能**：
- 设置环境变量
- 初始化 Ray
- 注册 CVE 环境
- 启动训练循环

### train_launcher.py

训练启动器，负责配置管理和命令构建。

**主要方法**：
- `check_prerequisites()`：检查前置条件
- `prepare_environment()`：准备环境
- `build_config()`：构建配置
- `build_command()`：构建命令行参数
- `launch()`：启动训练

---

# CVE-bench 测试

训练完成后，使用 CVE-bench 测试集评估模型的漏洞利用能力。

## CVE-bench 简介

CVE-bench 是一个评估 AI Agent 识别和利用真实世界 Web 应用漏洞能力的基准测试集，包含 40+ 个关键严重性的 CVE 挑战。

**测试变体**：
- **zero_day**：不提供漏洞详情，只告知目标地址，测试模型的漏洞发现能力
- **one_day**：提供漏洞的详细描述，测试模型的漏洞利用能力

**攻击类型**：
1. 拒绝服务攻击 (DoS)
2. 文件系统访问
3. 文件创建
4. 数据库修改
5. 数据库访问
6. 管理员账户攻陷
7. 用户权限提升
8. 出站服务利用

## 测试前置要求

### 1. 安装 CVE-bench

```bash
# 在 SecurityRL 同级目录克隆 CVE-bench
cd ~/PycharmProjects/SecurityRL
git clone https://github.com/uiuc-kang-lab/cve-bench.git
cd cve-bench
uv sync --dev
```

### 2. 确保训练完成

训练完成后，checkpoint 会保存在 `~/checkpoints/cve_agent/global_step_XXX` 目录。

## 运行测试

### 快速开始

```bash
cd dataset/dataset

# 使用最新 checkpoint 运行所有变体测试
python test_launcher.py

# 指定 checkpoint
python test_launcher.py --checkpoint ~/checkpoints/cve_agent/global_step_100

# 只运行 zero_day 变体
python test_launcher.py --variants zero_day

# 只运行 one_day 变体
python test_launcher.py --variants one_day

# 运行特定 CVE 挑战
python test_launcher.py --challenges CVE-2024-2624,CVE-2024-2771
```

### 完整参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--checkpoint` | 最新 checkpoint | Checkpoint 目录路径 |
| `--variants` | `zero_day,one_day` | 测试变体（逗号分隔） |
| `--challenges` | 全部 | 特定 CVE 挑战（逗号分隔） |
| `--max-messages` | `30` | 每个挑战的最大消息数 |
| `--setup-only` | - | 只安装 CVE-bench，不运行测试 |
| `--skip-check` | - | 跳过前置条件检查 |

### 首次运行

首次运行时，测试启动器会自动：
1. 检查 CVE-bench 是否已安装
2. 安装依赖（`uv sync --dev`）
3. 复制模型提供者到 CVE-bench
4. 创建模型注册入口

```bash
# 首次运行建议先 setup
python test_launcher.py --setup-only

# 然后运行测试
python test_launcher.py
```

## 测试结果

测试结果保存在 `eval_results/` 目录：

```
eval_results/
└── eval_YYYYMMDD_HHMMSS.json
```

**结果格式**：
```json
{
  "timestamp": "20241223_120000",
  "checkpoint": "/home/user/checkpoints/cve_agent/global_step_100",
  "variants": ["zero_day", "one_day"],
  "challenges": null,
  "returncode": 0,
  "stdout": "...",
  "stderr": "..."
}
```

## 评估指标

| 指标 | 说明 |
|------|------|
| Success Rate | 成功利用的 CVE 数量 / 总 CVE 数量 |
| Zero-day Rate | 在 zero_day 变体中的成功率 |
| One-day Rate | 在 one_day 变体中的成功率 |
| Attack Category | 按攻击类型分类的成功率 |

## 模型提供者

`lora_model_provider.py` 实现了 Inspect AI 的 `ModelAPI` 接口，将训练好的 LoRA 模型注册为 Inspect 兼容的模型提供者。

**使用方式**：
```bash
# 在 Inspect 中使用
inspect eval task.py --model=cve_lora/model -M checkpoint_path=/path/to/checkpoint
```

**参数**：
| 参数 | 默认值 | 说明 |
|------|--------|------|
| `checkpoint_path` | - | LoRA checkpoint 路径 |
| `base_model` | `Qwen/Qwen2.5-3B-Instruct` | 基础模型 |
| `device` | `auto` | 设备 |
| `torch_dtype` | `bfloat16` | 数据类型 |
| `max_new_tokens` | `2048` | 最大生成 token 数 |

## 常见问题

### 1. CVE-bench 容器启动失败

```bash
# 手动检查容器健康状态
cd ../cve-bench
./run test-health CVE-2024-2624

# 手动启动/停止容器
./run up CVE-2024-2624
./run down CVE-2024-2624
```

### 2. 模型加载失败

确保 checkpoint 目录结构正确：
```
global_step_XXX/
├── policy/
│   ├── adapter_config.json
│   └── adapter_model.safetensors
└── trainer_state.json
```

### 3. GPU 内存不足

测试时模型会完整加载到 GPU，确保有足够显存（约 10-15GB for 3B 模型）。

## 目录结构

```
SecurityRL/
├── dataset/
│   └── dataset/
│       ├── train_launcher.py      # 训练启动器
│       ├── test_launcher.py       # 测试启动器
│       ├── lora_model_provider.py # Inspect 模型提供者
│       └── eval_results/          # 测试结果
└── cve-bench/                     # CVE-bench 仓库（同级目录）
    ├── run
    └── src/
        ├── cvebench/
        └── critical/
            └── challenges/
```

## 许可证

MIT License
