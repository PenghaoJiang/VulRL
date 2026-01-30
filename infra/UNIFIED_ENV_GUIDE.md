# 统一环境使用指南

## 概述

VulRL 现在支持统一的安全环境接口，可以无缝集成 Vulhub 和 CTF 数据，实现跨环境的能力迁移。

### 核心特性

- ✅ **标准化接口**：遵循 Gymnasium 规范
- ✅ **多数据源支持**：Vulhub、CTF (CVE-bench)、自定义环境
- ✅ **返回值一致**：所有环境返回相同格式
- ✅ **向后兼容**：保留现有训练流程
- ✅ **易于扩展**：插件化适配器设计

---

## 快速开始

### 1. 数据集转换

首先将现有数据转换为统一格式：

```bash
# 转换 Vulhub 数据集
python dataset/dataset_converter.py vulhub \
    --input ~/data/cve_vulhub/train.parquet \
    --output ~/unified_tasks/vulhub \
    --format json

# 转换 CVE-bench 数据
python dataset/dataset_converter.py cvebench \
    --input ~/benchmark/cve-bench \
    --output ~/unified_tasks/ctf \
    --variant zero_day
```

### 2. 直接使用环境

```python
from infra.security_env import SecurityEnv
from infra.env_types import StandardAction, ActionType

# Vulhub 任务配置
vulhub_config = {
    "task_id": "CVE-2024-1234",
    "task_type": "vulhub",
    "max_steps": 30,
    "target_host": "apache",
    "target_port": 80,
    "backend_config": {
        "vulhub_path": "apache/CVE-2024-1234"
    },
    "poc_info": {...}
}

# 创建环境
env = SecurityEnv(config=vulhub_config)

# Gymnasium 风格使用
observation, info = env.reset()
print(f"Task: {observation.to_text()}")

# 执行动作
action = StandardAction(
    action_type=ActionType.BASH,
    arguments={"command": "nmap -p 80 target"}
)

obs, reward, terminated, truncated, info = env.step(action)
print(f"Output: {obs.to_text()}")
print(f"Reward: {reward}, Done: {terminated or truncated}")

env.close()
```

### 3. 训练使用

现有的训练流程无需修改：

```bash
# 使用现有的 train_launcher.py
python infra/train_launcher.py
```

训练器会自动使用新的统一环境。

---

## 环境配置格式

### 统一配置结构

```json
{
  "task_id": "CVE-2024-XXXX",
  "task_type": "vulhub",  // 或 "ctf"
  "max_steps": 30,
  "timeout": 30,
  "target_host": "target",
  "target_port": 80,
  "target_protocol": "http",
  "evaluation_config": {
    "ground_truth_images": ["path/to/gt.png"],
    "success_indicators": ["shell spawned", "admin access"],
    "expected_final_state": "RCE achieved"
  },
  "poc_info": {
    "exploit_steps": [...],
    "success_indicators": [...],
    "vulnerability_type": "rce"
  },
  "backend_config": {
    // Vulhub 特定
    "vulhub_path": "apache/CVE-2024-XXXX"

    // CTF 特定
    "compose_path": "path/to/compose.yml",
    "eval_config_path": "path/to/eval.yml"
  }
}
```

---

## 适配器系统

### 已支持的适配器

#### 1. VulhubAdapter

用于 Vulhub 环境：

```python
{
    "task_type": "vulhub",
    "backend_config": {
        "vulhub_path": "apache/CVE-2024-1234"
    }
}
```

#### 2. CTFAdapter

支持三种启动方式：

**Docker Compose (CVE-bench)**
```python
{
    "task_type": "ctf",
    "backend_config": {
        "compose_path": "~/cve-bench/src/critical/challenges/CVE-2024-XXXX/compose.yml",
        "eval_config_path": "~/cve-bench/src/critical/challenges/CVE-2024-XXXX/eval.yml"
    }
}
```

**Dockerfile**
```python
{
    "task_type": "ctf",
    "backend_config": {
        "dockerfile_path": "~/ctf/web_001/Dockerfile"
    }
}
```

**预构建镜像**
```python
{
    "task_type": "ctf",
    "backend_config": {
        "image_name": "ctf/web_challenge:latest"
    }
}
```

### 注册自定义适配器

```python
from infra.security_env import SecurityEnv
from infra.env_adapter import BaseEnvAdapter

class MyCustomAdapter(BaseEnvAdapter):
    def setup(self):
        # 启动环境
        pass

    def teardown(self):
        # 清理环境
        pass

    def reset_backend(self):
        # 返回任务描述
        return "Task description"

    def step_backend(self, action):
        # 执行动作
        output = "Command output"
        return output, 0.0, False, {}

    def _get_target_info(self):
        return {"host": "localhost", "port": 8080}

# 注册适配器
SecurityEnv.register_adapter("custom", MyCustomAdapter)

# 使用
env = SecurityEnv(config={"task_type": "custom", ...})
```

---

## 数据转换详解

### Vulhub 数据转换

```bash
python dataset/dataset_converter.py vulhub \
    --input ~/data/cve_vulhub/train.parquet \
    --output ~/unified_tasks/vulhub \
    --format json
```

**输出**：
- 每个 CVE 一个 JSON 文件
- 文件名：`CVE-XXXX-YYYY.json`
- 自动提取：vulhub_path, poc_info, success_indicators

### CVE-bench 数据转换

```bash
python dataset/dataset_converter.py cvebench \
    --input ~/benchmark/cve-bench \
    --output ~/unified_tasks/ctf \
    --variant zero_day  # 或 one_day
```

**输出**：
- 每个 challenge 一个 JSON 文件
- 自动解析：eval.yml, metadata, compose.yml 路径
- 提取 prompt 和 success indicators

### 自定义 CTF 数据转换

```bash
python dataset/dataset_converter.py custom-ctf \
    --input ~/ctf_data.json \
    --output ~/unified_tasks/ctf
```

**输入格式**：
```json
[
  {
    "id": "web_001",
    "host": "localhost",
    "port": 8080,
    "dockerfile_path": "~/ctf/web_001/Dockerfile",
    "description": "SQL injection challenge",
    "success_indicators": ["flag{"],
    "max_steps": 20
  }
]
```

---

## 混合训练

### 准备混合数据集

1. 转换 Vulhub 数据：
```bash
python dataset/dataset_converter.py vulhub \
    --input ~/data/cve_vulhub/train.parquet \
    --output ~/unified_tasks/vulhub
```

2. 转换 CTF 数据：
```bash
python dataset/dataset_converter.py cvebench \
    --input ~/benchmark/cve-bench \
    --output ~/unified_tasks/ctf
```

### 修改训练配置

在 `train_launcher.py` 中，可以指定多个数据路径：

```python
# 在 build_command() 中
params = [
    # 混合数据源
    f"++data.train_data=['{vulhub_dir}/*.json', '{ctf_dir}/*.json']",

    # 其他配置...
]
```

### 运行训练

```bash
python infra/train_launcher.py
```

Agent 将在 Vulhub 和 CTF 环境之间切换训练，学习通用的漏洞利用能力。

---

## 测试和验证

### 单元测试

测试 VulhubAdapter：
```python
from infra.vulhub_adapter import VulhubAdapter
from infra.env_types import StandardAction, ActionType

config = {
    "task_id": "CVE-2024-1234",
    "task_type": "vulhub",
    "backend_config": {"vulhub_path": "apache/CVE-2024-1234"}
}

adapter = VulhubAdapter(config)
adapter.setup()

obs, info = adapter.reset()
print(f"Observation type: {type(obs)}")
assert obs.text != ""

action = StandardAction(ActionType.BASH, {"command": "ls"})
obs, reward, term, trunc, info = adapter.step(action)
print(f"Output: {obs.to_text()}")

adapter.teardown()
```

测试 CTFAdapter：
```python
from infra.ctf_adapter import CTFAdapter

config = {
    "task_id": "CVE-2024-XXXX",
    "task_type": "ctf",
    "backend_config": {
        "compose_path": "~/cve-bench/.../compose.yml",
        "eval_config_path": "~/cve-bench/.../eval.yml"
    }
}

adapter = CTFAdapter(config)
# 测试流程同上
```

### 集成测试

测试完整环境：
```python
from infra.security_env import SecurityEnv

# 测试 Vulhub
env = SecurityEnv(config=vulhub_config)
obs, info = env.reset()
obs, reward, term, trunc, info = env.step(action)
env.close()

# 测试 CTF
env = SecurityEnv(config=ctf_config)
obs, info = env.reset()
obs, reward, term, trunc, info = env.step(action)
env.close()
```

---

## 故障排除

### 问题 1：Docker 网络连接失败

**症状**：attacker 容器无法访问目标

**解决**：
1. 检查网络配置：`docker network ls`
2. 确保容器在同一网络
3. 使用容器名而非 localhost

### 问题 2：适配器初始化失败

**症状**：`Unknown task type: xxx`

**解决**：
1. 检查 `task_type` 拼写
2. 确保适配器已注册：`SecurityEnv.list_adapters()`
3. 如果是自定义适配器，需要先注册

### 问题 3：奖励计算错误

**症状**：奖励始终为 0

**解决**：
1. 检查 `poc_info` 是否正确设置
2. 确保 `cve_exploit_env.py` 的奖励组件可导入
3. 查看日志中的奖励计算输出

### 问题 4：数据转换失败

**症状**：converter 报错

**解决**：
1. 检查输入文件路径
2. 确保 parquet/yaml 文件格式正确
3. 查看详细错误信息

---

## API 参考

### StandardObservation

```python
@dataclass
class StandardObservation:
    text: str                           # 文本观察
    target_info: Dict[str, Any]         # 目标信息
    environment_state: Dict[str, Any]   # 环境状态
    metadata: Dict[str, Any]            # 元数据

    def to_dict() -> Dict
    def to_text() -> str
```

### StandardAction

```python
@dataclass
class StandardAction:
    action_type: ActionType             # BASH 或 HTTP_REQUEST
    arguments: Dict[str, Any]           # 参数字典

    @classmethod
    def from_dict(action_dict: Dict) -> StandardAction

    @classmethod
    def from_json(json_str: str) -> StandardAction
```

### StandardInfo

```python
@dataclass
class StandardInfo:
    step: int                           # 当前步数
    max_steps: int                      # 最大步数
    task_id: str                        # 任务 ID
    task_type: str                      # 任务类型
    tool_executed: Optional[str]        # 执行的工具
    execution_time: float               # 执行时间
    final_evaluation: Optional[Dict]    # 最终评估
    extra: Dict[str, Any]               # 额外信息

    def to_dict() -> Dict
```

### SecurityEnv

```python
class SecurityEnv:
    def __init__(config: Union[Dict, StandardEnvConfig])

    def reset(seed=None, options=None) -> Tuple[StandardObservation, StandardInfo]

    def step(action: Union[str, Dict, StandardAction]) -> Tuple[
        StandardObservation, float, bool, bool, StandardInfo
    ]

    def close()

    @classmethod
    def register_adapter(task_type: str, adapter_class: type)

    @classmethod
    def list_adapters() -> list
```

---

## 下一步

1. **添加更多数据源**：NYU Bench, HackTheBox 等
2. **优化奖励机制**：针对 CTF 任务调整奖励计算
3. **自动 Ground Truth**：自动生成成功截图
4. **多 GPU 训练**：扩展到多卡并行
5. **性能优化**：减少环境启动时间

---

## 贡献

欢迎贡献新的适配器！请参考 `BaseEnvAdapter` 的文档和现有适配器的实现。

---

## 许可证

MIT License
