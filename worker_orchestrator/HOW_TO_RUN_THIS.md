# Worker Orchestrator 运行说明

## 一、简介

本目录 `worker_orchestrator` 提供 **Worker Router**（FastAPI + Redis 任务调度）与 **Worker Unit**（在子进程中执行漏洞利用 rollout）。SkyRL 侧通过 `ez_generator` 中的 HTTP 客户端把训练时的 rollout 交给本机 **Worker Router**（默认 **`http://localhost:12345`**）。

典型用法需要：

- **Linux / WSL**，`bash`、`python3`（建议与现有 `venv` 一致：**Python 3.12**）
- **Redis 服务端**（`redis-server` / `redis-cli`，非 pip 安装）
- 训练流水线依赖 **SkyRL**（`VulRL/SkyRL/skyrl-train`）与 **`uv`**（用于 `uv run` 启动训练）

以下命令均以 **仓库根目录**（即包含 `worker_orchestrator/` 与 `SkyRL/` 的那一层）为起点。

---

## 二、安装与配置

### 1. Python 虚拟环境与 Worker Router 依赖

在仓库根目录执行：

```bash
cd /path/to/VulRL
bash worker_orchestrator/setup.sh
```

该脚本会创建/使用 `worker_orchestrator/venv`，并按 `worker_orchestrator/requirements.txt` 安装依赖。

### 2. 可选：vLLM（本地大模型服务），不起skyrl单独调试worker unit时使用

若需使用 `start_llm_server.sh` 等本地 vLLM，在同一 venv 中执行：

```bash
cd /path/to/VulRL
bash worker_orchestrator/install_vllm.sh
```

（读取 `worker_orchestrator/requirements-llm.txt`，其中 vLLM 版本已固定。）

### 3. Redis（操作系统包）

`start_worker_router.sh` 会在本机尝试启动 `redis-server`，需系统已安装 Redis，例如：

```bash
# Ubuntu / Debian
sudo apt-get update && sudo apt-get install -y redis-server

# Fedora
sudo dnf install -y redis

# macOS（Homebrew）
brew install redis
```

`setup.sh` 结束时若检测不到 `redis-cli` 也会打印类似提示。

### 4. uv（SkyRL 训练入口使用）

训练脚本通过 **`uv run`** 调用 SkyRL，需单独安装 `uv`，例如：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安装后请按安装程序提示将 `uv` 加入 `PATH`（或新开终端）。官方文档：<https://docs.astral.sh/uv/getting-started/installation/>

### 5. SkyRL 与路径变量

确保仓库内存在 **`SkyRL/skyrl-train`**。运行训练前请编辑 **`worker_orchestrator/ez_generator/run_vulrl_skyrl.sh`** 中的路径（脚本内默认值多为作者机器路径，需改为你本机的 `VulRL` 根路径及模型、数据、checkpoint 目录）。

---

## 三、终端运行

训练进程会访问本机 **`http://localhost:12345`** 上的 Worker Router。因此：**请保证在运行下方第二段（SkyRL）命令时，Worker Router 已在运行**；最稳妥做法是 **先** 在另一终端执行 **第一段**（启动 Worker Router），**再** 执行第二段。

### 第一段：启动 Worker Router（含 Redis 清理与拉起）

```bash
cd /path/to/VulRL
bash worker_orchestrator/start_worker_router.sh
```

### 第二段：SkyRL / VulRL 训练启动

（需已安装 `uv`。）启动前可在 **编辑脚本** 或 **在运行前导出环境变量** 的方式调整下列变量（带 `${VAR:-默认值}` 的项支持用环境变量覆盖默认值；脚本里写死赋值的项只能改脚本）。

`worker_orchestrator/ez_generator/run_vulrl_skyrl.sh` 中的变量一览：

| 变量名 | 含义 / 备注 |
|--------|-------------|
| `MODEL_PATH` | 本地模型目录；可用环境变量覆盖，默认见脚本 |
| `MODEL_NAME` | 无本地模型时用作 HuggingFace 名；可用环境变量覆盖 |
| `WORKER_ROUTER_URL` | 仅用于 `echo` 展示；真实地址在 `WorkerRouterClient` 中写死为 `http://localhost:12345` |
| `TRAIN_DATA` | 训练 parquet 路径；可用环境变量覆盖 |
| `EPOCHS` | 训练 epoch 数 |
| `N_SAMPLES_PER_PROMPT` | 每 prompt 采样数 |
| `TRAIN_BATCH_SIZE` | 训练 batch |
| `EVAL_BATCH_SIZE` | 评估 batch |
| `MAX_STEPS` | 单条 rollout 最大步数（传入 `generator.max_turns`） |
| `LEARNING_RATE` | 学习率 |
| `NUM_GPUS` | 每节点 policy/ref GPU 数及本地 vLLM 引擎数等 |
| `CHECKPOINT_DIR` | checkpoint 目录 |
| `GPU_MEMORY_UTILIZATION` | 本地 vLLM `gpu_memory_utilization`（脚本内为普通赋值，非 `${…:-}`） |
| `LOGGER` | 日志后端：`local` / `wandb` / `tensorboard`（脚本内默认 `wandb`） |
| `PROJECT_NAME` | 实验项目名 |
| `RUN_NAME` | 单次运行名（默认带时间戳） |
| `WORKER_ORCHESTRATOR_PATH` | `worker_orchestrator` 根路径（脚本内写死，需改成你的仓库路径） |
| `EZ_GENERATOR_PATH` | 由 `WORKER_ORCHESTRATOR_PATH/ez_generator` 派生 |
| `SKYRL_PATH` | `skyrl-train` 根目录（脚本内写死） |
| `VULRL_INSIDE_SKYRL_PATH` | 同步 `ez_generator` 代码的目标目录，默认 `SKYRL_PATH/vulrl_inside_skyrl_v2` |

脚本运行过程中还会设置或依赖：

| 名称 | 含义 / 备注 |
|------|-------------|
| `MODEL_TO_USE` | 脚本内根据是否存在 `MODEL_PATH` 在 **`MODEL_PATH` 与 `MODEL_NAME` 之间选择**，勿在脚本外单独配置 |
| `RAY_EXPERIMENTAL_NOSET_CUDA_VISIBLE_DEVICES` | 导出为 `1`（固定） |
| `CUDA_VISIBLE_DEVICES` | 导出为 `0`（固定；与 `NUM_GPUS` 逻辑并行时注意） |
| `WANDB_API_KEY` | 未设置时默认为占位串；可用环境变量覆盖 |
| `WANDB_MODE` | 导出为 `disabled`（固定） |
| `PYTHONPATH` | 前置 `SKYRL_PATH`，便于导入 `skyrl_train` |

Hydra 覆盖项（如 `data.train_data`、`trainer.*`、`generator.*`）在脚本末尾 **`uv run …`** 中写死或引用上表变量；需要更多覆盖可在命令后追加参数（脚本末尾 `"$@"`）。

```bash
cd /path/to/VulRL
bash worker_orchestrator/ez_generator/run_vulrl_skyrl.sh
```

说明：`start_worker_router.sh` 会激活 `worker_orchestrator/venv`，尝试清理旧 worker、按需启动 Redis，并在 **`0.0.0.0:12345`** 上启动 `uvicorn`（与 `WorkerRouterClient` 默认地址一致）。该脚本在前台运行，占用当前终端；训练请在 **另一个终端** 执行第二段命令。

---

## 附：依赖关系摘要（便于排查）

| 组件 | 作用 |
|------|------|
| `worker_orchestrator/setup.sh` | 创建 venv，安装 `requirements.txt` |
| `worker_orchestrator/start_worker_router.sh` | Redis + Worker Router（端口 **12345**） |
| `worker_orchestrator/ez_generator/run_vulrl_skyrl.sh` | 同步代码到 SkyRL 目录、`cd` 到 `skyrl-train`、`uv run` 启动训练 |

训练侧 Python 依赖主要来自 **SkyRL 的 `uv` 环境**；Worker Router 侧来自 **`worker_orchestrator/venv`**。
