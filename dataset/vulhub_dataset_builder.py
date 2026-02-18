"""
Vulhub Dataset Builder v2.0
从 Vulhub 解析数据并生成训练数据集

核心特性：
1. 全面理解 README（文本 + 代码块 + 图片 OCR）
2. 生成完整可执行的 Python PoC 脚本
3. LLM 逻辑验证确保 PoC 正确性
4. 以 PoC 为中心的数据集结构
"""

import os
import re
import json
import yaml
import hashlib
import base64
import time
import subprocess
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum

import pandas as pd
from openai import OpenAI
import docker

# OCR 相关导入（可选依赖）
try:
    import pytesseract
    from PIL import Image
    OCR_AVAILABLE = True
except ImportError:
    OCR_AVAILABLE = False
    print("Warning: pytesseract or Pillow not installed. OCR will be disabled.")


# ============================================================================
# 数据类定义
# ============================================================================

class VulnerabilityType(str, Enum):
    """漏洞类型枚举"""
    RCE = "remote_code_execution"
    SQLI = "sql_injection"
    SSTI = "server_side_template_injection"
    PATH_TRAVERSAL = "path_traversal"
    DESERIALIZATION = "deserialization"
    FILE_UPLOAD = "file_upload"
    AUTH_BYPASS = "authentication_bypass"
    SSRF = "server_side_request_forgery"
    XXE = "xml_external_entity"
    XSS = "cross_site_scripting"
    FILE_INCLUSION = "file_inclusion"
    COMMAND_INJECTION = "command_injection"
    OTHER = "other"


@dataclass
class CodeBlock:
    """README 中提取的代码块"""
    language: str          # python, bash, shell, curl, http 等
    content: str           # 代码内容
    context: str           # 上下文说明（代码块前后的文字）
    line_number: int = 0   # 在 README 中的位置


@dataclass
class ImageContent:
    """图片 OCR 提取内容"""
    image_path: str        # 图片文件路径
    ocr_text: str          # pytesseract 提取的文字
    description: str       # 图片内容描述
    is_success_indicator: bool = False  # 是否展示成功利用


@dataclass
class ReadmeAnalysis:
    """README 综合分析结果"""
    raw_text: str                       # 原始 README 文本
    vulnerability_type: str             # 漏洞类型
    service_name: str                   # 服务名称
    service_version: str                # 受影响版本
    vulnerability_description: str      # 漏洞描述
    environment_setup: str              # 环境搭建说明
    exploitation_steps: List[Dict]      # 利用步骤
    success_indicators: List[str]       # 成功标志
    code_blocks: List[CodeBlock] = field(default_factory=list)
    images: List[ImageContent] = field(default_factory=list)
    reference_links: List[str] = field(default_factory=list)


@dataclass
class DockerConfig:
    """Docker 配置信息"""
    compose_path: str
    services: Dict[str, Any]
    exposed_ports: List[int]
    primary_port: int
    primary_service: str
    environment_vars: Dict[str, str] = field(default_factory=dict)


@dataclass
class GeneratedPoC:
    """生成的 PoC 脚本"""
    script: str                         # 完整 Python 脚本
    script_hash: str                    # SHA256 哈希
    dependencies: List[str]             # pip 依赖
    execution_cmd: str                  # 执行命令模板
    expected_output: str                # 预期输出描述
    validation_status: str              # llm_passed/llm_failed/docker_verified/docker_failed/failed
    validation_notes: str               # 验证说明
    generation_model: str               # 使用的模型
    generation_timestamp: str           # 生成时间
    llm_attempts: int = 0              # LLM 自检尝试次数
    # Docker 实战验证字段
    docker_verified: bool = False       # 是否通过 Docker 实战验证
    docker_stdout: str = ""             # Docker 验证时的 stdout
    docker_stderr: str = ""             # Docker 验证时的 stderr
    docker_exit_code: int = -1          # PoC 退出码
    docker_attempts: int = 0            # Docker 验证尝试次数


@dataclass
class VulhubEntry:
    """完整的 Vulhub 条目 - 核心数据结构"""
    # 标识信息
    cve_id: str
    vulhub_path: str

    # 内容分析
    readme_analysis: ReadmeAnalysis
    docker_config: DockerConfig

    # 生成的 PoC
    poc_script: Optional[GeneratedPoC] = None

    # 原始 PoC 文件
    original_poc_files: Dict[str, str] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """PoC LLM 自检结果（二元判定：正确/不正确）"""
    is_valid: bool                      # 是否正确
    issues: List[Dict]                  # 发现的具体问题
    missing_steps: List[str]            # 缺失的步骤
    summary: str                        # 一句话总结


@dataclass
class DockerVerificationResult:
    """Docker 实战验证结果"""
    success: bool                       # 最终判定
    exit_code: int                      # PoC 退出码
    stdout: str                         # 标准输出
    stderr: str                         # 标准错误
    indicators_matched: List[str]       # 匹配到的 success_indicators
    execution_time: float               # PoC 执行耗时
    environment_ready: bool             # Docker 环境是否成功启动
    error_message: str                  # 错误信息（如果有）


# ============================================================================
# OCR 处理器
# ============================================================================

class OCRProcessor:
    """图片 OCR 处理器"""

    def __init__(self, openai_client: OpenAI = None):
        self.client = openai_client

    def extract_text(self, image_path: Path) -> str:
        """使用 pytesseract 提取图片文字"""
        if not OCR_AVAILABLE:
            return ""

        try:
            image = Image.open(image_path)
            # 转换为 RGB 模式（处理 PNG 透明通道）
            if image.mode in ('RGBA', 'P'):
                image = image.convert('RGB')
            text = pytesseract.image_to_string(image, lang='eng+chi_sim')
            return text.strip()
        except Exception as e:
            print(f"  Warning: OCR failed for {image_path}: {e}")
            return ""

    def describe_image(self, image_path: Path, ocr_text: str) -> ImageContent:
        """生成图片描述"""
        description = f"Image at {image_path.name}"
        is_success = False

        # 基于 OCR 文本推断
        if ocr_text:
            success_keywords = ['success', 'pwned', 'root', 'admin', 'rce',
                              'command executed', 'shell', 'flag', 'id=0']
            if any(kw in ocr_text.lower() for kw in success_keywords):
                is_success = True
                description = f"Screenshot showing successful exploitation. OCR content: {ocr_text[:200]}"
            else:
                description = f"Screenshot with content: {ocr_text[:200]}"

        return ImageContent(
            image_path=str(image_path),
            ocr_text=ocr_text,
            description=description,
            is_success_indicator=is_success
        )


# ============================================================================
# 内容解析器
# ============================================================================

class ContentParser:
    """README 内容解析器"""

    def __init__(self, ocr_processor: OCRProcessor = None):
        self.ocr = ocr_processor or OCRProcessor()

    def extract_code_blocks(self, markdown: str) -> List[CodeBlock]:
        """从 Markdown 中提取所有代码块"""
        code_blocks = []

        # 匹配带语言标记的代码块：```language\ncode\n```
        pattern = r'```(\w*)\n(.*?)```'

        for match in re.finditer(pattern, markdown, re.DOTALL):
            language = match.group(1) or 'text'
            content = match.group(2).strip()

            # 获取上下文（代码块前 100 个字符）
            start_pos = match.start()
            context_start = max(0, start_pos - 150)
            context = markdown[context_start:start_pos].strip()
            # 只保留最后一行作为上下文
            context_lines = context.split('\n')
            context = context_lines[-1] if context_lines else ""

            code_blocks.append(CodeBlock(
                language=language.lower(),
                content=content,
                context=context,
                line_number=markdown[:start_pos].count('\n') + 1
            ))

        return code_blocks

    def extract_images(self, markdown: str, cve_path: Path) -> List[Path]:
        """从 Markdown 中提取图片路径"""
        images = []
        pattern = r'!\[.*?\]\((.*?)(?:\s+".*?")?\)'

        for match in re.findall(pattern, markdown):
            if match.startswith(('http://', 'https://')):
                continue
            img_path = cve_path / match
            if img_path.exists():
                images.append(img_path)

        return images

    def find_existing_poc_files(self, cve_path: Path) -> Dict[str, str]:
        """查找目录中已有的 PoC 文件"""
        poc_files = {}
        poc_patterns = ['poc.py', 'poc.xml', 'poc.sh', 'exploit.py',
                       'exploit.sh', 'payload.xml', 'poc.txt']

        for pattern in poc_patterns:
            poc_path = cve_path / pattern
            if poc_path.exists():
                try:
                    content = poc_path.read_text(encoding='utf-8')
                    poc_files[pattern] = content
                except Exception:
                    pass

        # 同时查找其他可能的 PoC 文件
        for file_path in cve_path.iterdir():
            if file_path.is_file() and file_path.suffix in ['.py', '.sh', '.xml']:
                name = file_path.name.lower()
                if 'poc' in name or 'exploit' in name or 'payload' in name:
                    if file_path.name not in poc_files:
                        try:
                            poc_files[file_path.name] = file_path.read_text(encoding='utf-8')
                        except Exception:
                            pass

        return poc_files

    def extract_reference_links(self, markdown: str) -> List[str]:
        """提取参考链接"""
        links = []
        # 匹配 Markdown 链接格式
        pattern = r'<(https?://[^>]+)>|\[([^\]]+)\]\((https?://[^)]+)\)'

        for match in re.finditer(pattern, markdown):
            url = match.group(1) or match.group(3)
            if url:
                links.append(url)

        return links

    def parse_readme(self, readme_path: Path, cve_path: Path) -> Tuple[str, List[CodeBlock], List[ImageContent], List[str]]:
        """解析 README 文件"""
        try:
            content = readme_path.read_text(encoding='utf-8')
        except Exception:
            return "", [], [], []

        # 提取代码块
        code_blocks = self.extract_code_blocks(content)

        # 提取并处理图片
        image_paths = self.extract_images(content, cve_path)
        images = []
        for img_path in image_paths:
            ocr_text = self.ocr.extract_text(img_path)
            image_content = self.ocr.describe_image(img_path, ocr_text)
            images.append(image_content)

        # 提取参考链接
        links = self.extract_reference_links(content)

        return content, code_blocks, images, links

    def parse_docker_compose(self, compose_path: Path) -> DockerConfig:
        """解析 docker-compose.yml"""
        try:
            with open(compose_path) as f:
                config = yaml.safe_load(f)

            services = config.get('services', {})
            if not services:
                return DockerConfig(
                    compose_path=str(compose_path),
                    services={},
                    exposed_ports=[80],
                    primary_port=80,
                    primary_service='web'
                )

            # 获取第一个服务作为主服务
            primary_service = list(services.keys())[0]
            service_config = services[primary_service]

            # 解析端口
            ports = []
            port_mappings = service_config.get('ports', [])
            for port in port_mappings:
                port_str = str(port)
                if ':' in port_str:
                    # 格式: "host:container" 或 "host:container/protocol"
                    container_port = port_str.split(':')[-1].split('/')[0]
                    ports.append(int(container_port))
                else:
                    ports.append(int(port_str.split('/')[0]))

            primary_port = ports[0] if ports else 80

            # 获取环境变量
            env_vars = {}
            env_list = service_config.get('environment', [])
            if isinstance(env_list, list):
                for item in env_list:
                    if '=' in str(item):
                        key, value = str(item).split('=', 1)
                        env_vars[key] = value
            elif isinstance(env_list, dict):
                env_vars = env_list

            return DockerConfig(
                compose_path=str(compose_path),
                services=services,
                exposed_ports=ports,
                primary_port=primary_port,
                primary_service=primary_service,
                environment_vars=env_vars
            )

        except Exception as e:
            print(f"  Warning: Failed to parse docker-compose: {e}")
            return DockerConfig(
                compose_path=str(compose_path),
                services={},
                exposed_ports=[80],
                primary_port=80,
                primary_service='web'
            )


# ============================================================================
# JSON 容错解析
# ============================================================================

# Tinker 默认配置
TINKER_BASE_URL = "https://tinker.thinkingmachines.dev/services/tinker-prod/oai/api/v1"
TINKER_DEFAULT_MODEL = "Qwen/Qwen3-235B-A22B-Instruct-2507"


def parse_json_response(text: str) -> Dict:
    """
    容错解析 LLM 返回的 JSON。
    处理常见情况：
      1. 纯 JSON
      2. ```json ... ``` 包裹
      3. 前后有解释文字
    """
    text = text.strip()

    # 尝试 1：直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试 2：提取 ```json ... ``` 代码块
    match = re.search(r'```(?:json)?\s*\n?(.*?)```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 尝试 3：找到第一个 { 和最后一个 } 之间的内容
    first_brace = text.find('{')
    last_brace = text.rfind('}')
    if first_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(text[first_brace:last_brace + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Failed to parse JSON from LLM response: {text[:200]}...")


# ============================================================================
# PoC 生成器
# ============================================================================

class PoCGenerator:
    """PoC 脚本生成器"""

    README_ANALYSIS_PROMPT = """You are a security expert analyzing a Vulhub CVE documentation.

## Input Materials

### README Content:
{readme_content}

### Code Blocks Extracted from README:
{code_blocks}

### OCR Text from Images:
{ocr_content}

### Existing PoC Files in Directory:
{existing_poc_files}

### Docker Configuration:
- Primary Port: {primary_port}
- Primary Service: {primary_service}

### CVE ID: {cve_id}

## Task
Analyze ALL provided materials and extract comprehensive vulnerability information.

## Output as JSON:
{{
  "vulnerability_type": "string (rce/sqli/ssti/path_traversal/deserialization/file_upload/auth_bypass/ssrf/xxe/xss/file_inclusion/command_injection/other)",
  "service_name": "string (e.g., Apache ActiveMQ, WordPress, nginx)",
  "service_version": "string (e.g., 5.17.3, < 2.4.50)",
  "vulnerability_description": "string (brief description of the vulnerability)",
  "environment_setup": "string (how to set up the environment)",
  "exploitation_steps": [
    {{
      "step_number": 1,
      "description": "string (what to do)",
      "action_type": "string (http_request/socket/command/upload/inject)",
      "technical_details": {{
        "method": "string (GET/POST/PUT/etc, if HTTP)",
        "endpoint": "string (target path)",
        "payload": "string (the actual payload)",
        "headers": {{}},
        "notes": "string (any important notes)"
      }},
      "expected_observation": "string (what you should see)"
    }}
  ],
  "success_indicators": ["string (observable evidence of success)"],
  "required_dependencies": ["string (pip package names ONLY, e.g., \"requests\", \"pwntools\". Do NOT add descriptions or parentheses. Do NOT include standard library modules like os, sys, json, re, time, argparse, hashlib, base64, urllib)"],
  "difficulty": "string (easy/medium/hard)"
}}

Important:
- Be VERY specific about exploitation steps based on the README and existing PoC code
- Extract actual payloads, endpoints, and parameters from the documentation
- If existing PoC files are provided, analyze their logic carefully
- Output ONLY valid JSON, no other text"""

    POC_GENERATION_PROMPT = """You are a security expert writing a Python PoC (Proof of Concept) script.

## Vulnerability Analysis:
{vulnerability_analysis}

## Existing PoC Reference (if available):
{existing_poc}

## README Code Blocks:
{code_blocks}

## Requirements

Generate a COMPLETE, EXECUTABLE Python script that exploits this vulnerability.

### Script Requirements:
1. **Standalone executable** - Can run directly with `python3 poc.py`
2. **Command-line arguments** using argparse:
   - `--host` or `--target`: Target host (required)
   - `--port`: Target port (with sensible default based on vulnerability)
   - Any other necessary parameters
3. **Clear output messages**:
   - `[+]` prefix for successful steps
   - `[-]` prefix for failures
   - `[*]` prefix for informational messages
4. **Error handling** - Catch and handle common errors gracefully
5. **Comments** - Explain key parts of the exploit

### Code Structure Template:
```python
#!/usr/bin/env python3
\"\"\"
{cve_id} PoC - {service_name} {vulnerability_type}
{brief_description}

Usage: python3 poc.py --host TARGET_HOST --port TARGET_PORT
\"\"\"

import argparse
import requests  # or other necessary imports
# ... other imports

def exploit(host: str, port: int, **kwargs) -> bool:
    \"\"\"
    Main exploitation function.

    Args:
        host: Target host IP/hostname
        port: Target port

    Returns:
        True if exploitation successful, False otherwise
    \"\"\"
    target_url = f"http://{{host}}:{{port}}"

    # Step 1: ...
    print(f"[*] Targeting {{target_url}}")

    # Implement exploitation logic here
    # ...

    return True  # or False

def main():
    parser = argparse.ArgumentParser(
        description='{cve_id} PoC',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument('--host', '-H', required=True, help='Target host')
    parser.add_argument('--port', '-p', type=int, default={default_port}, help='Target port')
    # Add more arguments as needed

    args = parser.parse_args()

    print(f"[*] {cve_id} Exploit")
    print(f"[*] Target: {{args.host}}:{{args.port}}")

    try:
        success = exploit(args.host, args.port)
        if success:
            print("[+] Exploitation successful!")
        else:
            print("[-] Exploitation failed")
    except KeyboardInterrupt:
        print("\\n[-] Interrupted by user")
    except Exception as e:
        print(f"[-] Error: {{e}}")

if __name__ == "__main__":
    main()
```

## Output
Generate ONLY the complete Python script. No explanations before or after.
The script must be syntactically correct and executable.
Start with #!/usr/bin/env python3"""

    POC_VALIDATION_PROMPT = """You are a security expert reviewing a generated PoC script.

## Original README Content:
{readme_content}

## Vulnerability Analysis:
{vulnerability_analysis}

## Generated PoC Script:
```python
{generated_poc}
```

## Your Task
Check whether this PoC script is CORRECT and can exploit the vulnerability as described.

Specifically check:
1. Are the exploitation steps complete? (endpoints, payloads, parameters, headers)
2. Are HTTP methods, URL paths, and payload formats correct?
3. Is the script syntactically valid and executable?
4. Are the steps in the correct order with proper dependencies?

## IMPORTANT: Issue Reporting Rules
If you find issues, you MUST be SPECIFIC and CONCRETE:
- BAD: "payload construction has flaws" (vague, useless)
- GOOD: "Line `payload = f'{{{{cmd}}}}'` should be `payload = f'O:1:\"S\":1:{{{{s:4:\"cmd\";s:{{{{len(cmd)}}}}:\"{{{{cmd}}}}\";}}}}' ` because the vulnerability requires PHP serialized object format"
- BAD: "output verification is unreliable" (vague)
- GOOD: "Line `if 'success' in resp.text` should check for the command output like `if 'uid=0' in resp.text` because the exploit runs `id` command"

Each issue must include: the exact code that is wrong, why it is wrong, and the exact fix.

## Output as JSON:
{{
  "is_valid": true/false,
  "issues": [
    {{
      "wrong_code": "string (the exact line or snippet that is wrong)",
      "reason": "string (why it is wrong, with technical detail)",
      "fix": "string (the exact corrected code)"
    }}
  ],
  "missing_steps": ["string (specific step that is missing, e.g. 'Must send POST to /login first to get session cookie before exploiting /vuln endpoint')"],
  "summary": "string (one sentence: why it is correct or what is the most critical problem)"
}}

If the script is correct, set is_valid=true and leave issues and missing_steps as empty arrays."""

    def __init__(self, api_key: str = None, model: str = None,
                 api_base: str = None):
        api_key = api_key or os.getenv("TINKER_API_KEY") or os.getenv("OPENAI_API_KEY")
        api_base = api_base or os.getenv("TINKER_API_BASE") or TINKER_BASE_URL
        self.client = OpenAI(api_key=api_key, base_url=api_base)
        self.model = model or TINKER_DEFAULT_MODEL

    def analyze_readme(self, entry: VulhubEntry) -> Dict:
        """分析 README 内容，提取结构化信息"""
        # 准备代码块信息
        code_blocks_text = ""
        for i, cb in enumerate(entry.readme_analysis.code_blocks):
            code_blocks_text += f"\n### Code Block {i+1} ({cb.language}):\n"
            code_blocks_text += f"Context: {cb.context}\n"
            code_blocks_text += f"```{cb.language}\n{cb.content}\n```\n"

        # 准备 OCR 内容
        ocr_content = ""
        for img in entry.readme_analysis.images:
            if img.ocr_text:
                ocr_content += f"\n### Image: {Path(img.image_path).name}\n"
                ocr_content += f"OCR Text: {img.ocr_text}\n"
                ocr_content += f"Description: {img.description}\n"

        # 准备现有 PoC 文件
        existing_poc_text = ""
        for filename, content in entry.original_poc_files.items():
            existing_poc_text += f"\n### {filename}:\n```\n{content}\n```\n"

        prompt = self.README_ANALYSIS_PROMPT.format(
            readme_content=entry.readme_analysis.raw_text[:6000],
            code_blocks=code_blocks_text or "No code blocks found",
            ocr_content=ocr_content or "No OCR content available",
            existing_poc_files=existing_poc_text or "No existing PoC files",
            primary_port=entry.docker_config.primary_port,
            primary_service=entry.docker_config.primary_service,
            cve_id=entry.cve_id
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a security expert. You MUST output ONLY valid JSON, no explanations, no markdown, no extra text before or after the JSON object."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )

            return parse_json_response(response.choices[0].message.content)
        except Exception as e:
            print(f"  Warning: README analysis failed: {e}")
            return {
                "vulnerability_type": "other",
                "service_name": entry.docker_config.primary_service,
                "service_version": "unknown",
                "vulnerability_description": "",
                "environment_setup": "",
                "exploitation_steps": [],
                "success_indicators": [],
                "required_dependencies": ["requests"],
                "difficulty": "medium"
            }

    def generate_poc(self, entry: VulhubEntry, analysis: Dict, feedback: str = None) -> GeneratedPoC:
        """生成 Python PoC 脚本"""
        # 准备现有 PoC 参考
        existing_poc = ""
        if entry.original_poc_files:
            # 优先使用 poc.py
            if 'poc.py' in entry.original_poc_files:
                existing_poc = entry.original_poc_files['poc.py']
            else:
                # 使用第一个找到的 PoC
                existing_poc = list(entry.original_poc_files.values())[0]

        # 准备代码块
        code_blocks_text = ""
        for cb in entry.readme_analysis.code_blocks:
            if cb.language in ['python', 'bash', 'shell', 'sh', 'curl']:
                code_blocks_text += f"\n```{cb.language}\n{cb.content}\n```\n"

        prompt = self.POC_GENERATION_PROMPT.format(
            vulnerability_analysis=json.dumps(analysis, indent=2, ensure_ascii=False),
            existing_poc=existing_poc or "No existing PoC available",
            code_blocks=code_blocks_text or "No relevant code blocks",
            cve_id=entry.cve_id,
            service_name=analysis.get('service_name', 'Unknown'),
            vulnerability_type=analysis.get('vulnerability_type', 'vulnerability'),
            brief_description=analysis.get('vulnerability_description', ''),
            default_port=entry.docker_config.primary_port
        )

        if feedback:
            prompt += f"\n\n## Previous Issues (MUST FIX):\n{feedback}"

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a security expert writing Python exploit code. Output only the Python script, nothing else."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )

            script = response.choices[0].message.content.strip()

            # 清理脚本（移除可能的 markdown 标记）
            if script.startswith('```python'):
                script = script[9:]
            elif script.startswith('```'):
                script = script[3:]
            if script.endswith('```'):
                script = script[:-3]
            script = script.strip()

            # 确保脚本以 shebang 开头
            if not script.startswith('#!/'):
                script = '#!/usr/bin/env python3\n' + script

            # 计算哈希
            script_hash = hashlib.sha256(script.encode()).hexdigest()[:16]

            return GeneratedPoC(
                script=script,
                script_hash=script_hash,
                dependencies=analysis.get('required_dependencies', ['requests']),
                execution_cmd=f"python3 poc.py --host {{host}} --port {entry.docker_config.primary_port}",
                expected_output=', '.join(analysis.get('success_indicators', [])),
                validation_status="pending",
                validation_notes="",
                generation_model=self.model,
                generation_timestamp=datetime.now().isoformat()
            )

        except Exception as e:
            print(f"  Error: PoC generation failed: {e}")
            return GeneratedPoC(
                script="# Generation failed",
                script_hash="",
                dependencies=[],
                execution_cmd="",
                expected_output="",
                validation_status="failed",
                validation_notes=str(e),
                generation_model=self.model,
                generation_timestamp=datetime.now().isoformat()
            )


# ============================================================================
# PoC 验证器
# ============================================================================

class PoCValidator:
    """PoC 脚本验证器（LLM 自检：二元判定）"""

    MAX_RETRIES = 3

    def __init__(self, api_key: str = None, model: str = None,
                 api_base: str = None):
        api_key = api_key or os.getenv("TINKER_API_KEY") or os.getenv("OPENAI_API_KEY")
        api_base = api_base or os.getenv("TINKER_API_BASE") or TINKER_BASE_URL
        self.client = OpenAI(api_key=api_key, base_url=api_base)
        self.model = model or TINKER_DEFAULT_MODEL

    def validate(self, entry: VulhubEntry, analysis: Dict) -> ValidationResult:
        """验证生成的 PoC，返回二元判定（正确/不正确）"""
        if not entry.poc_script or entry.poc_script.script == "# Generation failed":
            return ValidationResult(
                is_valid=False,
                issues=[{"description": "No PoC script generated", "suggested_fix": "Regenerate"}],
                missing_steps=[],
                summary="No valid PoC script to validate"
            )

        prompt = PoCGenerator.POC_VALIDATION_PROMPT.format(
            readme_content=entry.readme_analysis.raw_text[:4000],
            vulnerability_analysis=json.dumps(analysis, indent=2, ensure_ascii=False),
            generated_poc=entry.poc_script.script
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are a security expert reviewing exploit code. You MUST output ONLY valid JSON, no explanations, no markdown, no extra text before or after the JSON object."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.1
            )

            result = parse_json_response(response.choices[0].message.content)

            return ValidationResult(
                is_valid=result.get('is_valid', False),
                issues=result.get('issues', []),
                missing_steps=result.get('missing_steps', []),
                summary=result.get('summary', '')
            )

        except Exception as e:
            print(f"  Warning: LLM validation failed: {e}")
            return ValidationResult(
                is_valid=False,
                issues=[{"description": f"Validation error: {e}", "suggested_fix": "Retry"}],
                missing_steps=[],
                summary=f"LLM validation error: {e}"
            )

    def build_feedback(self, validation: ValidationResult) -> str:
        """将自检发现的问题格式化为反馈文本"""
        feedback_parts = []

        if validation.issues:
            feedback_parts.append("## Issues found by LLM self-check (MUST FIX ALL):\n")
            for i, issue in enumerate(validation.issues, 1):
                feedback_parts.append(f"### Issue {i}:")
                if issue.get('wrong_code'):
                    feedback_parts.append(f"Wrong code: `{issue['wrong_code']}`")
                if issue.get('reason'):
                    feedback_parts.append(f"Reason: {issue['reason']}")
                if issue.get('fix'):
                    feedback_parts.append(f"Fix: `{issue['fix']}`")
                # 兼容旧格式
                if issue.get('description'):
                    feedback_parts.append(f"Problem: {issue['description']}")
                if issue.get('suggested_fix'):
                    feedback_parts.append(f"Fix: {issue['suggested_fix']}")
                feedback_parts.append("")

        if validation.missing_steps:
            feedback_parts.append("## Missing steps:")
            for step in validation.missing_steps:
                feedback_parts.append(f"- {step}")

        feedback_parts.append(f"\nSummary: {validation.summary}")

        return '\n'.join(feedback_parts)


# ============================================================================
# Docker PoC 验证器
# ============================================================================

class DockerPoCVerifier:
    """Docker 实战 PoC 验证器 - 在真实漏洞环境中执行 PoC"""

    DOCKER_MAX_RETRIES = 3
    ATTACKER_IMAGE = "cve-attacker:latest"

    def __init__(self, poc_timeout: int = 60, service_wait: int = 60):
        self.poc_timeout = poc_timeout
        self.service_wait = service_wait
        self.docker_client = docker.from_env()
        self.compose_cmd = self._detect_compose_command()

    def _detect_compose_command(self) -> List[str]:
        """检测可用的 docker compose 命令"""
        # 优先使用 docker compose (v2 plugin)
        try:
            subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True, check=True, timeout=10
            )
            return ["docker", "compose"]
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
            pass
        # 回退到 docker-compose (v1 standalone)
        if shutil.which("docker-compose"):
            return ["docker-compose"]
        raise RuntimeError("Neither 'docker compose' nor 'docker-compose' found")

    def verify(self, entry: VulhubEntry, poc_script: str, analysis: Dict) -> DockerVerificationResult:
        """
        主验证方法：启动 Docker 环境 → 执行 PoC → 分析结果 → 清理
        """
        compose_path = Path(entry.docker_config.compose_path)
        sanitized_id = re.sub(r'[^a-z0-9]', '', entry.cve_id.lower())
        project_name = f"vulpoc-{sanitized_id}-{int(time.time()) % 100000}"

        target_host = entry.docker_config.primary_service
        target_port = entry.docker_config.primary_port
        success_indicators = analysis.get("success_indicators", [])
        poc_deps = analysis.get("required_dependencies", [])

        attacker = None
        network_name = None

        try:
            # Step 1: 启动漏洞环境
            print(f"      [Docker] Starting environment ({compose_path.parent.name})...")
            network_name = self._start_environment(compose_path, project_name)
            if not network_name:
                return DockerVerificationResult(
                    success=False, exit_code=-1, stdout="", stderr="",
                    indicators_matched=[], execution_time=0.0,
                    environment_ready=False,
                    error_message="Failed to start Docker environment"
                )

            # Step 2: 创建 attacker 容器
            print(f"      [Docker] Creating attacker container...")
            attacker = self._create_attacker(network_name, poc_deps, project_name)

            # Step 3: 等待目标服务就绪
            print(f"      [Docker] Waiting for {target_host}:{target_port}...")
            service_ready = self._wait_for_service(attacker, target_host, target_port)
            if not service_ready:
                return DockerVerificationResult(
                    success=False, exit_code=-1, stdout="", stderr="",
                    indicators_matched=[], execution_time=0.0,
                    environment_ready=False,
                    error_message=f"Service {target_host}:{target_port} not ready after {self.service_wait}s"
                )

            # Step 4: 执行 PoC
            print(f"      [Docker] Executing PoC...")
            start_time = time.time()
            exit_code, stdout, stderr = self._execute_poc(
                attacker, poc_script, target_host, target_port
            )
            execution_time = time.time() - start_time

            # Step 5: 分析结果
            is_success, matched = self._analyze_results(
                exit_code, stdout, stderr, success_indicators
            )

            status_str = "SUCCESS" if is_success else "FAILED"
            print(f"      [Docker] Result: {status_str} (exit_code={exit_code}, "
                  f"matched={len(matched)}, time={execution_time:.1f}s)")

            return DockerVerificationResult(
                success=is_success,
                exit_code=exit_code,
                stdout=stdout[-4000:],   # 保留更多输出供反馈
                stderr=stderr[-4000:],   # 保留完整 traceback
                indicators_matched=matched,
                execution_time=execution_time,
                environment_ready=True,
                error_message="" if is_success else f"PoC exited with code {exit_code}"
            )

        except Exception as e:
            print(f"      [Docker] Error: {e}")
            return DockerVerificationResult(
                success=False, exit_code=-1, stdout="", stderr=str(e),
                indicators_matched=[], execution_time=0.0,
                environment_ready=False,
                error_message=str(e)
            )
        finally:
            self._cleanup(project_name, compose_path, attacker)

    def _start_environment(self, compose_path: Path, project_name: str) -> Optional[str]:
        """根据 sample 的 docker-compose.yml 启动环境，返回网络名"""
        compose_dir = compose_path.parent
        try:
            cmd = self.compose_cmd + [
                "-f", str(compose_path),
                "-p", project_name,
                "up", "-d"
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=120, cwd=str(compose_dir)
            )
            if result.returncode != 0:
                print(f"      [Docker] compose up failed: {result.stderr[:500]}")
                return None

            # 获取网络名：project_name + _default
            network_name = f"{project_name}_default"

            # 验证网络存在
            try:
                self.docker_client.networks.get(network_name)
            except docker.errors.NotFound:
                # 尝试列出相关网络
                networks = self.docker_client.networks.list(
                    names=[f"{project_name}"]
                )
                if networks:
                    network_name = networks[0].name
                else:
                    print(f"      [Docker] Network not found, using default name")

            return network_name

        except subprocess.TimeoutExpired:
            print(f"      [Docker] compose up timed out (120s)")
            return None
        except Exception as e:
            print(f"      [Docker] Failed to start environment: {e}")
            return None

    def _create_attacker(self, network_name: str, poc_deps: List[str],
                         project_name: str) -> docker.models.containers.Container:
        """创建 attacker 容器并挂到同一网络"""
        container_name = f"{project_name}-attacker"

        # 确保 attacker 镜像存在，否则使用 python:3.11-slim
        try:
            self.docker_client.images.get(self.ATTACKER_IMAGE)
            image = self.ATTACKER_IMAGE
        except docker.errors.ImageNotFound:
            image = "python:3.11-slim"
            # 确保 python 镜像存在
            try:
                self.docker_client.images.get(image)
            except docker.errors.ImageNotFound:
                print(f"      [Docker] Pulling {image}...")
                self.docker_client.images.pull(image)

        attacker = self.docker_client.containers.run(
            image,
            command="sleep 3600",
            name=container_name,
            network=network_name,
            detach=True,
            remove=False
        )

        # 安装 PoC 依赖
        # 标准库模块，不需要 pip install
        stdlib = {"argparse", "os", "sys", "json", "re", "time", "hashlib",
                  "base64", "urllib", "socket", "struct", "io", "string",
                  "collections", "itertools", "functools", "pathlib",
                  "subprocess", "threading", "http", "html", "xml", "csv"}
        # 清洗依赖名：只保留合法 pip 包名（字母、数字、-、_、.）
        cleaned_deps = []
        for dep in poc_deps:
            # 取第一个单词（去掉括号注释等）
            dep_name = dep.split("(")[0].split("#")[0].split(",")[0].strip()
            # 只保留合法字符
            dep_name = re.sub(r'[^a-zA-Z0-9\-_.]', '', dep_name)
            if dep_name and dep_name.lower() not in stdlib:
                cleaned_deps.append(dep_name)
        all_deps = list(set(["requests"] + cleaned_deps))
        if all_deps:
            dep_str = " ".join(all_deps)
            exec_result = attacker.exec_run(
                ["pip", "install", "--quiet", "--disable-pip-version-check"] + all_deps
            )
            if exec_result.exit_code != 0:
                print(f"      [Docker] pip install warning: {exec_result.output.decode('utf-8', errors='replace')[:200]}")

        return attacker

    def _wait_for_service(self, attacker, target_host: str, target_port: int) -> bool:
        """在 attacker 容器内等待目标服务就绪，使用指数退避"""
        wait_intervals = [1, 2, 4, 8, 8, 8, 8, 8, 8]  # 总计约 55 秒
        elapsed = 0

        for interval in wait_intervals:
            if elapsed >= self.service_wait:
                break
            # 使用 python 进行端口检测（比 curl 更可靠，因为目标不一定是 HTTP）
            check_cmd = (
                f"python3 -c \""
                f"import socket; s=socket.socket(); s.settimeout(3); "
                f"s.connect(('{target_host}', {target_port})); "
                f"s.close(); print('OK')\""
            )
            result = attacker.exec_run(["sh", "-c", check_cmd])
            if result.exit_code == 0:
                return True
            time.sleep(interval)
            elapsed += interval

        return False

    def _execute_poc(self, attacker, poc_script: str,
                     target_host: str, target_port: int) -> Tuple[int, str, str]:
        """在 attacker 容器内执行 PoC 脚本"""
        # 将脚本写入容器
        import tarfile
        import io

        # 创建 tar 流以 put_archive 方式写入
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            script_bytes = poc_script.encode('utf-8')
            info = tarfile.TarInfo(name='poc.py')
            info.size = len(script_bytes)
            tar.addfile(info, io.BytesIO(script_bytes))
        tar_stream.seek(0)

        attacker.put_archive('/tmp', tar_stream)

        # 执行 PoC（用 timeout 命令防止挂起）
        exec_result = attacker.exec_run(
            ["timeout", str(self.poc_timeout),
             "python3", "/tmp/poc.py", "--host", target_host, "--port", str(target_port)],
            demux=True
        )

        exit_code = exec_result.exit_code
        stdout_raw, stderr_raw = exec_result.output if isinstance(exec_result.output, tuple) else (exec_result.output, b"")
        stdout = (stdout_raw or b"").decode('utf-8', errors='replace')
        stderr = (stderr_raw or b"").decode('utf-8', errors='replace')

        return exit_code, stdout, stderr

    def _analyze_results(self, exit_code: int, stdout: str, stderr: str,
                         success_indicators: List[str]) -> Tuple[bool, List[str]]:
        """
        三级判定逻辑：
          Level 1: exit_code == 0
          Level 2: stdout 含 "[+] Exploitation successful!" 或 "[+]"
          Level 3: stdout 匹配 success_indicators 中的关键词
        """
        matched = []

        # Level 1: 退出码
        if exit_code != 0:
            return False, matched

        # Level 2: 脚本自报成功
        has_success_marker = False
        if "[+] Exploitation successful!" in stdout:
            has_success_marker = True
            matched.append("[+] Exploitation successful!")
        elif "[+]" in stdout:
            has_success_marker = True
            matched.append("[+] marker found")

        # Level 3: 匹配 success_indicators
        combined_output = stdout + stderr
        for indicator in success_indicators:
            if indicator.lower() in combined_output.lower():
                matched.append(indicator)

        # 判定：exit_code==0 且 (有成功标记 或 有 indicator 匹配)
        is_success = has_success_marker or len(matched) > 0
        return is_success, matched

    def _cleanup(self, project_name: str, compose_path: Path,
                 attacker=None):
        """清理 attacker 容器和 Docker 环境"""
        # 清理 attacker 容器
        if attacker:
            try:
                attacker.stop(timeout=5)
                attacker.remove(force=True)
            except Exception:
                pass

        # compose down
        try:
            cmd = self.compose_cmd + [
                "-f", str(compose_path),
                "-p", project_name,
                "down", "-v", "--remove-orphans"
            ]
            subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=30, cwd=str(compose_path.parent)
            )
        except Exception:
            pass

    def build_feedback(self, result: DockerVerificationResult) -> str:
        """将 Docker 验证结果格式化为反馈文本，供 PoCGenerator 重新生成"""
        parts = [
            "## Docker Execution Feedback (REAL environment test - THIS IS THE GROUND TRUTH)",
            f"Exit code: {result.exit_code}",
            f"Environment ready: {result.environment_ready}",
            f"Execution time: {result.execution_time:.1f}s",
        ]

        if result.error_message:
            parts.append(f"Error: {result.error_message}")

        # stdout 完整输出
        if result.stdout:
            parts.append(f"\n### stdout (complete):\n```\n{result.stdout}\n```")
        else:
            parts.append("\n### stdout: (empty - the script produced no output)")

        # stderr 完整输出（关键：包含 traceback）
        if result.stderr:
            parts.append(f"\n### stderr (complete - READ THIS CAREFULLY for errors and tracebacks):\n```\n{result.stderr}\n```")
        else:
            parts.append("\n### stderr: (empty)")

        if result.indicators_matched:
            parts.append(f"\nMatched indicators: {result.indicators_matched}")
        else:
            parts.append("\nNo success indicators matched in output.")

        # 根据 exit_code 和执行时间给出针对性提示
        hints = []
        if result.execution_time < 0.5:
            hints.append("- Script finished in <0.5s, likely crashed on startup (import error, syntax error, or immediate exception)")
        if result.exit_code == 1:
            hints.append("- Exit code 1: Python unhandled exception. Check stderr for the full traceback")
        if result.exit_code == 2:
            hints.append("- Exit code 2: Likely argparse error (wrong arguments) or syntax error")
        if result.exit_code == 124:
            hints.append("- Exit code 124: Script timed out. The exploit may be waiting for a response that never comes (wrong port? wrong endpoint?)")
        if not result.stdout and not result.stderr:
            hints.append("- No output at all: script may have been killed or failed to start")

        if hints:
            parts.append("\n### Diagnostic hints:\n" + "\n".join(hints))

        parts.append(
            "\n### Instructions:\n"
            "Fix the PoC based on the REAL execution output above. "
            "Pay close attention to stderr tracebacks - they show exactly where and why the script failed. "
            "The target service is accessible at the host:port passed via --host and --port arguments."
        )

        return "\n".join(parts)

    def save_verified_poc(self, poc_script: str, cve_path: Path) -> Path:
        """将通过验证的 PoC 保存到 sample 目录"""
        output_path = cve_path / "poc_verified.py"
        output_path.write_text(poc_script, encoding='utf-8')
        print(f"      [Docker] Saved verified PoC to: {output_path}")
        return output_path


# ============================================================================
# Vulhub 扫描器
# ============================================================================

class VulhubScanner:
    """Vulhub 仓库扫描器"""

    def __init__(self, vulhub_path: str):
        self.vulhub_path = Path(vulhub_path).expanduser()
        if not self.vulhub_path.exists():
            raise ValueError(f"Vulhub path not found: {vulhub_path}")

    def scan_all(self) -> List[Path]:
        """扫描所有有效的 CVE 目录"""
        valid_dirs = []

        for category in self.vulhub_path.iterdir():
            if not category.is_dir() or category.name.startswith('.'):
                continue

            for cve_dir in category.iterdir():
                if not cve_dir.is_dir() or cve_dir.name.startswith('.'):
                    continue

                if self._is_valid_cve_dir(cve_dir):
                    valid_dirs.append(cve_dir)

        return valid_dirs

    def _is_valid_cve_dir(self, cve_dir: Path) -> bool:
        """检查是否为有效的 CVE 目录"""
        # 必须有 README
        has_readme = any((cve_dir / name).exists()
                        for name in ['README.md', 'README.zh-cn.md', 'readme.md'])

        # 必须有 docker-compose
        has_compose = any((cve_dir / name).exists()
                         for name in ['docker-compose.yml', 'docker-compose.yaml'])

        return has_readme and has_compose

    def extract_cve_id(self, cve_path: Path) -> str:
        """从路径提取 CVE ID"""
        match = re.search(r'(CVE-\d{4}-\d+)', str(cve_path), re.IGNORECASE)
        if match:
            return match.group(1).upper()
        return f"{cve_path.parent.name}/{cve_path.name}"

    def find_readme(self, cve_path: Path) -> Optional[Path]:
        """查找 README 文件"""
        for name in ['README.md', 'README.zh-cn.md', 'readme.md']:
            readme = cve_path / name
            if readme.exists():
                return readme
        return None

    def find_compose(self, cve_path: Path) -> Optional[Path]:
        """查找 docker-compose 文件"""
        for name in ['docker-compose.yml', 'docker-compose.yaml']:
            compose = cve_path / name
            if compose.exists():
                return compose
        return None


# ============================================================================
# 数据集构建器
# ============================================================================

class DatasetBuilder:
    """数据集构建器"""

    def __init__(self, output_dir: str, api_key: str = None,
                 api_base: str = None, no_docker: bool = False):
        self.output_dir = Path(output_dir).expanduser()
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.no_docker = no_docker

        self.ocr_processor = OCRProcessor()
        self.content_parser = ContentParser(self.ocr_processor)
        self.poc_generator = PoCGenerator(api_key=api_key, api_base=api_base)
        self.poc_validator = PoCValidator(api_key=api_key, api_base=api_base)

        # Docker 验证器（按需初始化）
        self.docker_verifier = None
        if not no_docker:
            try:
                self.docker_verifier = DockerPoCVerifier()
                print("Docker verifier initialized successfully")
            except Exception as e:
                print(f"Warning: Docker verifier unavailable: {e}")
                print("Falling back to LLM-only validation")

    def process_cve(self, cve_path: Path, scanner: VulhubScanner,
                    skip_verified: bool = False) -> Optional[VulhubEntry]:
        """处理单个 CVE"""
        cve_id = scanner.extract_cve_id(cve_path)
        print(f"  Processing: {cve_id}")

        # --skip-verified: 跳过已有 poc_verified.py 的 sample
        if skip_verified and (cve_path / "poc_verified.py").exists():
            print(f"    Skipped: poc_verified.py already exists")
            return None

        # 查找文件
        readme_path = scanner.find_readme(cve_path)
        compose_path = scanner.find_compose(cve_path)

        if not readme_path or not compose_path:
            print(f"    Skipped: Missing README or docker-compose")
            return None

        # 解析内容
        readme_text, code_blocks, images, links = self.content_parser.parse_readme(
            readme_path, cve_path
        )
        docker_config = self.content_parser.parse_docker_compose(compose_path)
        original_poc_files = self.content_parser.find_existing_poc_files(cve_path)

        # 计算相对路径
        try:
            rel_path = str(cve_path.relative_to(scanner.vulhub_path))
        except ValueError:
            rel_path = str(cve_path)

        # 创建条目
        entry = VulhubEntry(
            cve_id=cve_id,
            vulhub_path=rel_path,
            readme_analysis=ReadmeAnalysis(
                raw_text=readme_text,
                vulnerability_type="",
                service_name="",
                service_version="",
                vulnerability_description="",
                environment_setup="",
                exploitation_steps=[],
                success_indicators=[],
                code_blocks=code_blocks,
                images=images,
                reference_links=links
            ),
            docker_config=docker_config,
            original_poc_files=original_poc_files
        )

        # 分析 README
        print(f"    Analyzing README...")
        analysis = self.poc_generator.analyze_readme(entry)

        # 更新分析结果
        entry.readme_analysis.vulnerability_type = analysis.get('vulnerability_type', 'other')
        entry.readme_analysis.service_name = analysis.get('service_name', '')
        entry.readme_analysis.service_version = analysis.get('service_version', '')
        entry.readme_analysis.vulnerability_description = analysis.get('vulnerability_description', '')
        entry.readme_analysis.environment_setup = analysis.get('environment_setup', '')
        entry.readme_analysis.exploitation_steps = analysis.get('exploitation_steps', [])
        entry.readme_analysis.success_indicators = analysis.get('success_indicators', [])

        print(f"    Type: {entry.readme_analysis.vulnerability_type}")
        print(f"    Service: {entry.readme_analysis.service_name}")

        # === Step 1: 生成初始 PoC ===
        print(f"    Generating PoC...")
        poc = self.poc_generator.generate_poc(entry, analysis)

        if poc.validation_status == "failed":
            print(f"    PoC generation failed")
            entry.poc_script = poc
            return entry

        # === Step 2: LLM 自检循环（二元：正确/不正确） ===
        print(f"    LLM self-check...")
        entry.poc_script = poc

        for llm_attempt in range(PoCValidator.MAX_RETRIES):
            validation = self.poc_validator.validate(entry, analysis)
            entry.poc_script.llm_attempts = llm_attempt + 1

            if validation.is_valid:
                entry.poc_script.validation_status = "llm_passed"
                entry.poc_script.validation_notes = validation.summary
                print(f"    LLM passed (attempt {llm_attempt + 1})")
                break

            # LLM 发现问题 → 用反馈修正后再检
            print(f"    LLM found issues (attempt {llm_attempt + 1}): {validation.summary}")
            feedback = self.poc_validator.build_feedback(validation)
            poc = self.poc_generator.generate_poc(entry, analysis, feedback)
            entry.poc_script = poc
        else:
            # LLM 自检多次仍有问题，标记但仍继续送 Docker 验证
            entry.poc_script.validation_status = "llm_failed"
            entry.poc_script.validation_notes = f"LLM self-check failed after {PoCValidator.MAX_RETRIES} attempts: {validation.summary}"
            print(f"    LLM self-check exhausted, proceeding to Docker anyway")

        # === Step 3-5: Docker 实战验证循环（最终判定） ===
        if self.docker_verifier and entry.poc_script.validation_status != "failed":
            print(f"    Docker verification...")
            docker_verified = False

            for docker_attempt in range(DockerPoCVerifier.DOCKER_MAX_RETRIES):
                print(f"    Docker attempt {docker_attempt + 1}/{DockerPoCVerifier.DOCKER_MAX_RETRIES}...")
                docker_result = self.docker_verifier.verify(
                    entry, entry.poc_script.script, analysis
                )

                if docker_result.success:
                    docker_verified = True
                    entry.poc_script.docker_verified = True
                    entry.poc_script.validation_status = "docker_verified"
                    entry.poc_script.docker_stdout = docker_result.stdout
                    entry.poc_script.docker_stderr = docker_result.stderr
                    entry.poc_script.docker_exit_code = docker_result.exit_code
                    entry.poc_script.docker_attempts = docker_attempt + 1
                    print(f"    Docker VERIFIED! (attempt {docker_attempt + 1})")
                    break

                # 用真实错误输出重新生成
                docker_feedback = self.docker_verifier.build_feedback(docker_result)
                print(f"    Docker failed, regenerating with real error feedback...")
                poc = self.poc_generator.generate_poc(entry, analysis, docker_feedback)
                entry.poc_script = poc

            # === Step 6: 保存验证通过的 PoC 到 sample 目录 ===
            if docker_verified:
                self.docker_verifier.save_verified_poc(entry.poc_script.script, cve_path)
            else:
                entry.poc_script.validation_status = "docker_failed"
                entry.poc_script.docker_attempts = DockerPoCVerifier.DOCKER_MAX_RETRIES
                print(f"    Docker verification failed after {DockerPoCVerifier.DOCKER_MAX_RETRIES} attempts")

        return entry

    def build(self, scanner: VulhubScanner, limit: int = None,
              skip_verified: bool = False) -> Path:
        """构建数据集"""
        cve_dirs = scanner.scan_all()
        print(f"Found {len(cve_dirs)} valid CVE directories")

        if limit:
            cve_dirs = cve_dirs[:limit]
            print(f"Processing first {limit} CVEs")

        entries = []
        failed = []

        for i, cve_path in enumerate(cve_dirs):
            print(f"\n[{i+1}/{len(cve_dirs)}]", end="")

            try:
                entry = self.process_cve(cve_path, scanner,
                                         skip_verified=skip_verified)
                if entry:
                    entries.append(entry)
            except Exception as e:
                print(f"    Error: {e}")
                failed.append((cve_path, str(e)))

        print(f"\n{'='*60}")
        print(f"Processed: {len(entries)} successful, {len(failed)} failed")

        # 转换为 DataFrame
        records = []
        for entry in entries:
            record = {
                # 标识信息
                "cve_id": entry.cve_id,
                "vulhub_path": entry.vulhub_path,

                # 漏洞元数据
                "vulnerability_type": entry.readme_analysis.vulnerability_type,
                "service_name": entry.readme_analysis.service_name,
                "service_version": entry.readme_analysis.service_version,
                "vulnerability_description": entry.readme_analysis.vulnerability_description,

                # 环境配置
                "primary_port": entry.docker_config.primary_port,
                "exposed_ports": json.dumps(entry.docker_config.exposed_ports),
                "primary_service": entry.docker_config.primary_service,

                # PoC 脚本（核心字段）
                "poc_script": entry.poc_script.script if entry.poc_script else "",
                "poc_dependencies": json.dumps(entry.poc_script.dependencies if entry.poc_script else []),
                "poc_execution_cmd": entry.poc_script.execution_cmd if entry.poc_script else "",

                # 利用步骤和成功标志
                "exploitation_steps": json.dumps(entry.readme_analysis.exploitation_steps, ensure_ascii=False),
                "success_indicators": json.dumps(entry.readme_analysis.success_indicators, ensure_ascii=False),

                # README 原始内容
                "readme_content": entry.readme_analysis.raw_text,

                # 代码块
                "code_blocks": json.dumps([asdict(cb) for cb in entry.readme_analysis.code_blocks], ensure_ascii=False),

                # 图片 OCR 内容
                "image_ocr_content": json.dumps([asdict(img) for img in entry.readme_analysis.images], ensure_ascii=False),

                # 原有 PoC 文件
                "original_poc_files": json.dumps(entry.original_poc_files, ensure_ascii=False),

                # 参考链接
                "reference_links": json.dumps(entry.readme_analysis.reference_links),

                # 验证元数据
                "validation_status": entry.poc_script.validation_status if entry.poc_script else "failed",
                "validation_notes": entry.poc_script.validation_notes if entry.poc_script else "",
                "llm_attempts": entry.poc_script.llm_attempts if entry.poc_script else 0,

                # Docker 验证元数据
                "docker_verified": entry.poc_script.docker_verified if entry.poc_script else False,
                "docker_stdout": entry.poc_script.docker_stdout if entry.poc_script else "",
                "docker_stderr": entry.poc_script.docker_stderr if entry.poc_script else "",
                "docker_exit_code": entry.poc_script.docker_exit_code if entry.poc_script else -1,
                "docker_attempts": entry.poc_script.docker_attempts if entry.poc_script else 0,

                # 生成元数据
                "generation_model": entry.poc_script.generation_model if entry.poc_script else "",
                "generation_timestamp": entry.poc_script.generation_timestamp if entry.poc_script else "",
            }
            records.append(record)

        # 保存
        output_path = self.output_dir / "train.parquet"
        df = pd.DataFrame(records)
        df.to_parquet(output_path, index=False)
        print(f"\nDataset saved to: {output_path}")
        print(f"Total samples: {len(records)}")

        # 保存失败记录
        if failed:
            error_path = self.output_dir / "errors.json"
            with open(error_path, 'w') as f:
                json.dump([{"path": str(p), "error": e} for p, e in failed], f, indent=2)
            print(f"Error log saved to: {error_path}")

        # 统计信息
        if records:
            llm_passed = sum(1 for r in records if r['validation_status'] == 'llm_passed')
            llm_failed = sum(1 for r in records if r['validation_status'] == 'llm_failed')
            docker_verified = sum(1 for r in records if r['docker_verified'])
            docker_failed = sum(1 for r in records if r['validation_status'] == 'docker_failed')
            gen_failed = sum(1 for r in records if r['validation_status'] == 'failed')
            print(f"\nValidation stats:")
            print(f"  LLM self-check passed: {llm_passed}")
            print(f"  LLM self-check failed: {llm_failed}")
            print(f"  Docker verified: {docker_verified}")
            print(f"  Docker failed: {docker_failed}")
            print(f"  Generation failed: {gen_failed}")

        return output_path


# ============================================================================
# 主函数
# ============================================================================

def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Vulhub Dataset Builder v2.0 - Generate PoC scripts from Vulhub CVEs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all CVEs with Tinker + Qwen3 (default)
  python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ~/data/cve_vulhub

  # Process first 10 CVEs (for testing)
  python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ~/data/cve_vulhub --limit 10

  # LLM-only mode (no Docker verification)
  python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ~/data/cve_vulhub --no-docker

  # Incremental run: skip already verified samples
  python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ~/data/cve_vulhub --skip-verified

  # Use a different OpenAI-compatible API
  python vulhub_dataset_builder.py --api_base https://api.openai.com/v1 --model gpt-4o --api_key sk-xxx
"""
    )
    parser.add_argument("--vulhub_path", type=str, default="~/vulhub",
                        help="Path to Vulhub repository (default: ~/vulhub)")
    parser.add_argument("--output_dir", type=str, default="~/data/cve_vulhub",
                        help="Output directory for dataset (default: ~/data/cve_vulhub)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of CVEs to process (for testing)")
    parser.add_argument("--model", type=str, default=None,
                        help=f"Model to use (default: {TINKER_DEFAULT_MODEL})")
    parser.add_argument("--api_key", type=str, default=None,
                        help="API key (default: from TINKER_API_KEY or OPENAI_API_KEY env)")
    parser.add_argument("--api_base", type=str, default=None,
                        help=f"API base URL (default: TINKER_API_BASE env or {TINKER_BASE_URL})")
    parser.add_argument("--no-docker", action="store_true",
                        help="Disable Docker verification (LLM-only mode)")
    parser.add_argument("--skip-verified", action="store_true",
                        help="Skip CVEs that already have poc_verified.py")

    args = parser.parse_args()

    # 解析 API 配置
    api_key = args.api_key or os.getenv("TINKER_API_KEY") or os.getenv("OPENAI_API_KEY")
    api_base = args.api_base or os.getenv("TINKER_API_BASE") or TINKER_BASE_URL
    model = args.model or TINKER_DEFAULT_MODEL

    print("=" * 60)
    print("Vulhub Dataset Builder v2.0")
    print("=" * 60)
    print(f"Vulhub path: {args.vulhub_path}")
    print(f"Output dir: {args.output_dir}")
    print(f"API base: {api_base}")
    print(f"Model: {model}")
    print(f"OCR available: {OCR_AVAILABLE}")
    print(f"Docker verification: {'disabled' if args.no_docker else 'enabled'}")
    print(f"Skip verified: {args.skip_verified}")
    if args.limit:
        print(f"Limit: {args.limit}")
    print("=" * 60)

    # 检查 API key
    if not api_key:
        print("Error: API key not found. Set TINKER_API_KEY (or OPENAI_API_KEY) environment variable or use --api_key")
        return 1

    try:
        # 初始化
        scanner = VulhubScanner(args.vulhub_path)
        builder = DatasetBuilder(args.output_dir, api_key=api_key,
                                 api_base=api_base, no_docker=args.no_docker)

        # 更新模型设置
        builder.poc_generator.model = model
        builder.poc_validator.model = model

        # 构建数据集
        output_path = builder.build(scanner, limit=args.limit,
                                    skip_verified=args.skip_verified)

        print("\n" + "=" * 60)
        print("Dataset built successfully!")
        print(f"Output: {output_path}")
        print("=" * 60)

        return 0

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
