# Vulhub Dataset Builder v2.0

从 Vulhub 仓库解析 CVE 信息，**自动生成可执行的 Python PoC 脚本**，通过 **Docker 实战验证**确保 PoC 正确性，并输出训练数据集。

## 核心特性

1. **全面理解 README** - 解析文本、代码块、图片（OCR）
2. **生成 Python PoC** - 完整可执行的漏洞利用脚本
3. **LLM 自检** - 二元判定（正确/不正确），发现问题则指出具体错误并修正
4. **Docker 验证** - 在真实漏洞环境中执行 PoC，以运行结果作为最终判定
5. **反馈循环** - Docker 执行失败时，将真实的 stdout/stderr/traceback 反馈给 LLM 重新生成

## 完整流程

```
对每个 CVE sample:

Step 1: 解析 README + docker-compose → LLM 分析漏洞信息 → 生成 PoC
        ↓
Step 2: LLM 自检（二元判定：正确/不正确）
        如果不正确 → 指出具体错误代码和修复方案 → 修正 → 再次自检
        最多重试 3 次，即使自检未通过也继续进入 Docker 验证
        ↓
Step 3: 根据 sample 的 docker-compose.yml 启动 Docker 漏洞环境
        在 attacker 容器内等待目标服务就绪
        ↓
Step 4: 在 attacker 容器内执行 PoC
        ↓
Step 5: 分析执行结果（exit_code + 输出标记 + success_indicators）
        │
        ├─ 成功 → Step 6
        │
        └─ 失败 → 将完整 stdout/stderr/traceback 作为反馈
                   → LLM 根据真实错误修正 PoC
                   → 清理 Docker 环境，重新启动（避免脏状态）
                   → 最多重试 3 次
        ↓
Step 6: 将验证通过的 PoC 保存到 sample 目录
        例如: ~/vulhub/elasticsearch/CVE-2014-3120/poc_verified.py
        同时记录到 train.parquet
        ↓
Step 7: 清理 Docker 环境
```

## 快速开始

### 前置条件

```bash
# 1. 安装 Python 依赖
pip install -r requirements.txt

# 2. 设置 Tinker API Key
export TINKER_API_KEY="your-tinker-api-key"

# 3. 克隆 Vulhub
git clone https://github.com/vulhub/vulhub.git ~/vulhub

# 4. 确认 Docker 正在运行
docker ps
```

### 运行

```bash
# 测试模式：处理前 3 个 CVE（含 Docker 验证）
python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ~/data/cve_vulhub --limit 3

# 处理所有 CVE
python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ~/data/cve_vulhub

# 增量运行：跳过已有 poc_verified.py 的 sample
python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ~/data/cve_vulhub --skip-verified

# 仅 LLM 验证（不启动 Docker，用于调试 API 连通性）
python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ~/data/cve_vulhub --limit 3 --no-docker

# 使用其他 OpenAI 兼容 API（如 OpenAI 原版）
python vulhub_dataset_builder.py --api_base https://api.openai.com/v1 --model gpt-4o --api_key sk-xxx
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--vulhub_path` | `~/vulhub` | Vulhub 仓库路径 |
| `--output_dir` | `~/data/cve_vulhub` | 输出数据集路径 |
| `--limit` | `None` | 限制处理的 CVE 数量（用于测试） |
| `--model` | `Qwen/Qwen3-235B-A22B-Instruct-2507` | 使用的 LLM 模型 |
| `--api_key` | `$TINKER_API_KEY` | API Key |
| `--api_base` | Tinker API URL | API base URL（支持任意 OpenAI 兼容接口） |
| `--no-docker` | `False` | 禁用 Docker 验证（仅 LLM 自检） |
| `--skip-verified` | `False` | 跳过已有 `poc_verified.py` 的 sample |

### 环境变量

| 变量 | 说明 |
|------|------|
| `TINKER_API_KEY` | Tinker API Key（优先） |
| `OPENAI_API_KEY` | OpenAI API Key（回退） |
| `TINKER_API_BASE` | 自定义 API base URL |

## 输出格式

### train.parquet 字段

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
| `validation_status` | str | 验证状态（见下表） |
| `validation_notes` | str | 验证说明 |
| `llm_attempts` | int | LLM 自检尝试次数 |
| `docker_verified` | bool | 是否通过 Docker 实战验证 |
| `docker_stdout` | str | Docker 执行时的 stdout |
| `docker_stderr` | str | Docker 执行时的 stderr |
| `docker_exit_code` | int | PoC 退出码 |
| `docker_attempts` | int | Docker 验证尝试次数 |
| `generation_model` | str | 使用的 LLM 模型 |
| `generation_timestamp` | str | 生成时间 (ISO 格式) |

### 验证状态

| 状态 | 说明 |
|------|------|
| `docker_verified` | PoC 通过 Docker 实战验证，已保存为 `poc_verified.py` |
| `docker_failed` | Docker 验证失败（重试 3 次后仍未通过） |
| `llm_passed` | LLM 自检通过（仅在 `--no-docker` 模式下出现） |
| `llm_failed` | LLM 自检未通过（仅在 `--no-docker` 模式下出现） |
| `failed` | PoC 生成失败 |

## 架构

### 处理流程

```
┌──────────────┐    ┌───────────────┐    ┌─────────────────┐
│ VulhubScanner │───>│ ContentParser │───>│   PoCGenerator  │
│              │    │               │    │                 │
│ - 扫描 CVE   │    │ - README 文本 │    │ - 分析漏洞信息   │
│ - 验证结构   │    │ - 代码块提取  │    │ - 生成 Python   │
│              │    │ - OCR 图片    │    │   PoC 脚本      │
└──────────────┘    └───────────────┘    └────────┬────────┘
                                                  │
                                                  ▼
┌───────────────┐    ┌────────────────────┐    ┌──────────────┐
│ DatasetBuilder │<───│ DockerPoCVerifier  │<───│ PoCValidator │
│               │    │                    │    │              │
│ - 输出        │    │ - compose up       │    │ - LLM 自检   │
│   parquet     │    │ - attacker 容器    │    │   (二元判定)  │
│ - 保存        │    │ - 执行 PoC        │    │ - 最多 3 次   │
│   poc_verified│    │ - 分析结果        │    │   重试        │
│ - 统计信息    │    │ - 反馈循环        │    │              │
└───────────────┘    └────────────────────┘    └──────────────┘
```

### 主要类

| 类名 | 功能 |
|------|------|
| `VulhubScanner` | 扫描 Vulhub 仓库中的有效 CVE 目录 |
| `ContentParser` | 解析 README（代码块、图片、链接）和 docker-compose |
| `OCRProcessor` | 使用 pytesseract 提取图片文字（可选） |
| `PoCGenerator` | 使用 LLM 分析 README 并生成 Python PoC 脚本 |
| `PoCValidator` | LLM 自检（二元判定：正确/不正确），提供具体修复建议 |
| `DockerPoCVerifier` | 在真实 Docker 漏洞环境中执行 PoC 并验证结果 |
| `DatasetBuilder` | 编排整个流程，管理 LLM 自检 + Docker 验证双循环 |

### 数据类

| 类名 | 功能 |
|------|------|
| `CodeBlock` | README 中的代码块（语言、内容、上下文） |
| `ImageContent` | 图片 OCR 内容和描述 |
| `ReadmeAnalysis` | README 综合分析结果 |
| `DockerConfig` | Docker 配置信息（服务、端口、环境变量） |
| `GeneratedPoC` | 生成的 PoC 脚本及验证元数据 |
| `VulhubEntry` | 完整的 Vulhub 条目（核心数据结构） |
| `ValidationResult` | LLM 自检结果（二元判定 + 具体问题列表） |
| `DockerVerificationResult` | Docker 实战验证结果（exit_code、stdout、stderr 等） |

## Docker 验证细节

### 验证判定逻辑（三级）

```
Level 1: exit_code == 0                                    → 脚本至少没报错
Level 2: stdout 含 "[+] Exploitation successful!" 或 "[+]" → 脚本自报成功
Level 3: stdout 匹配 success_indicators 中的关键词          → 与 LLM 分析的预期一致

最终判定：exit_code == 0 且 (Level 2 或 Level 3 匹配) → 成功
```

### PoC 执行方式

- PoC 在 **attacker 容器**内执行（与漏洞环境在同一 Docker 网络）
- 通过 `service_name:container_port` 访问目标，无需端口映射
- 每次 Docker 重试都会 `compose down -v` 后重新 `compose up -d`，避免脏状态

## 生成的 PoC 示例

```python
#!/usr/bin/env python3
"""
CVE-2016-3088 PoC - Apache ActiveMQ file_upload
The Fileserver application in Apache ActiveMQ allows arbitrary file write...

Usage: python3 poc.py --host TARGET_HOST --port TARGET_PORT
"""

import argparse
import requests

def exploit(host: str, port: int) -> bool:
    """Main exploitation function."""
    target_url = f"http://{host}:{port}"

    # Step 1: Upload webshell
    print(f"[*] Uploading webshell to {target_url}")
    # ... exploitation logic ...

    return True

def main():
    parser = argparse.ArgumentParser(description='CVE-2016-3088 PoC')
    parser.add_argument('--host', '-H', required=True, help='Target host')
    parser.add_argument('--port', '-p', type=int, default=8161, help='Target port')
    args = parser.parse_args()

    success = exploit(args.host, args.port)
    if success:
        print("[+] Exploitation successful!")
    else:
        print("[-] Exploitation failed")

if __name__ == "__main__":
    main()
```

## 常见问题

### 1. OCR Warning

```
Warning: OCR failed for ... tesseract is not installed
```

OCR 是**可选功能**，不影响 PoC 生成和验证。如果需要 OCR：
```bash
# Ubuntu
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim
```

### 2. API Key 未设置

```bash
export TINKER_API_KEY="your-tinker-api-key"
# 或使用命令行参数
python vulhub_dataset_builder.py --api_key "your-key"
```

### 3. Docker 不可用

确保 Docker 正在运行：
```bash
docker ps
```
如果 Docker 不可用，可以用 `--no-docker` 模式仅做 LLM 自检。

### 4. 内存不足

处理大量 CVE 时可能内存不足，使用 `--limit` 参数分批处理：
```bash
python vulhub_dataset_builder.py --limit 50
```

### 5. 增量运行

已验证通过的 CVE 会在 sample 目录下生成 `poc_verified.py`，重新运行时可跳过：
```bash
python vulhub_dataset_builder.py --skip-verified
```

## 依赖

- Python 3.10+
- openai >= 1.0.0（OpenAI 兼容 SDK，用于调用 Tinker API）
- docker >= 6.0.0（Docker SDK）
- pandas >= 2.0.0
- pyarrow >= 12.0.0
- pyyaml >= 6.0
- requests >= 2.28.0
- Pillow >= 10.0.0（可选，图片处理）
- pytesseract >= 0.3.10（可选，OCR）

## 许可证

MIT License
