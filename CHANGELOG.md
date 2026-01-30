# 更新日志

## [2.0.0] - 统一环境架构 - 2026-01-30

### 🎉 重大更新：统一环境接口层

实现了跨 Vulhub 和 CTF 数据源的统一环境架构，支持混合训练和能力迁移。

### ✨ 新增功能

#### 核心组件

- **标准化数据结构** (`infra/env_types.py`)
  - `StandardObservation`: 统一的观察值格式
  - `StandardAction`: 统一的动作格式
  - `StandardInfo`: 统一的 info 字典
  - `StandardEnvConfig`: 统一的环境配置

- **适配器系统**
  - `BaseEnvAdapter`: 适配器抽象基类，定义标准接口
  - `VulhubAdapter`: Vulhub 环境适配器
  - `CTFAdapter`: CTF 环境适配器（支持 CVE-bench、Dockerfile、镜像）

- **统一环境** (`infra/security_env.py`)
  - `SecurityEnv`: 遵循 Gymnasium 规范的统一环境类
  - 自动适配器路由（Vulhub/CTF）
  - 完整保留现有三层奖励机制
  - SkyRL 兼容

- **数据转换工具** (`dataset/dataset_converter.py`)
  - `VulhubToUnifiedConverter`: Vulhub parquet → 统一配置
  - `CTFToUnifiedConverter`: CVE-bench/CTF → 统一配置

#### 文档

- **使用指南** (`infra/UNIFIED_ENV_GUIDE.md`)
  - 完整的 API 参考文档
  - 混合训练教程
  - 自定义适配器开发指南
  - 故障排除

- **测试脚本** (`infra/test_unified_env.py`)
  - 基础功能测试
  - 适配器集成测试

### 🔧 修改的文件

- `infra/main_training.py`
  - 环境注册从 `CVEExploitEnv` 改为 `SecurityEnv`
  - 添加向后兼容支持

- `infra/train_launcher.py`
  - 更新注释，说明支持混合数据集

- `README.md`
  - 添加统一环境介绍
  - 更新架构图
  - 添加数据转换说明
  - 更新快速开始流程

### 💡 关键特性

**标准化接口**
- 所有环境类型返回完全一致的数据格式
- 遵循 Gymnasium 标准：`reset()` 和 `step()`
- Agent 只与标准接口交互，完全不感知底层差异

**能力迁移**
- 支持 Vulhub + CTF 混合训练
- Agent 学习通用漏洞利用能力
- 跨环境技能迁移

**易于扩展**
- 插件化适配器架构
- 新增数据源只需实现 `BaseEnvAdapter`
- 运行时动态注册：`SecurityEnv.register_adapter()`

**向后兼容**
- 完全保留现有奖励机制（StepJudge + TrajectoryJudge + LLM1Judge）
- 现有训练代码无需修改
- 支持旧的 `CVEExploitEnv` 环境名

### 📊 支持的数据源

| 数据源 | 适配器 | 启动方式 | 状态 |
|--------|--------|---------|------|
| Vulhub | `VulhubAdapter` | Docker Compose | ✅ 已实现 |
| CVE-bench | `CTFAdapter` | Docker Compose + eval.yml | ✅ 已实现 |
| Dockerfile | `CTFAdapter` | Dockerfile | ✅ 已实现 |
| 预构建镜像 | `CTFAdapter` | Docker image | ✅ 已实现 |
| 自定义 | 继承 `BaseEnvAdapter` | 可扩展 | ✅ 支持 |

### 🔄 迁移指南

#### 对现有用户

**无需任何修改**，现有训练流程完全兼容：

```bash
# 原有方式继续有效
python infra/train_launcher.py
```

#### 使用新功能

**混合训练**（推荐）：

```bash
# 1. 转换数据集
python dataset/dataset_converter.py vulhub --input train.parquet --output ~/unified_tasks/vulhub
python dataset/dataset_converter.py cvebench --input ~/cve-bench --output ~/unified_tasks/ctf

# 2. 修改 train_launcher.py 的数据路径（支持多个数据源）
# 3. 启动训练
python infra/train_launcher.py
```

### 🐛 已知限制

- Docker 环境必需（Vulhub 和 CTF 都需要）
- 奖励计算依赖 OpenAI API（GPT-4o/GPT-4o-mini）
- Ground Truth 图片需要手动准备

### 📝 下一步计划

- [ ] 添加更多 CTF 数据源（NYU Bench, HackTheBox）
- [ ] 优化 CTF 任务的奖励计算
- [ ] 自动生成 Ground Truth 截图
- [ ] 多 GPU 并行训练支持
- [ ] 环境启动时间优化

---

## [1.0.0] - 初始版本

### 特性

- Vulhub 环境支持
- LoRA 微调训练
- LLM-as-Judge 视觉评估
- 自动 PoC 生成
- CVE-bench 测试集成
