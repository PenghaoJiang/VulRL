"""
Vulhub Dataset Builder v2.0
从 Vulhub 解析数据并生成训练数据集

核心特性：
1. 全面理解 README（文本 + 代码块 + 图片 Vision API 直接处理）
2. 两层 IR 中间表示（事实层 + 可回放规格层）
3. 回放式 PoC 生成（翻译 spec，不重新发明 payload）
4. 逐项对账验证 + Docker 实战验证
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

# 图片处理（base64 编码，供 Vision API 使用）
import mimetypes


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
    """图片内容（base64 编码，供 Vision API 直接处理）"""
    image_path: str        # 图片文件路径
    base64_data: str       # base64 编码的图片数据
    mime_type: str          # MIME 类型 (image/png, image/jpeg 等)
    description: str       # 图片描述（文件名 + 上下文）
    ocr_text: str = ""     # 保留字段（兼容，不再使用 tesseract）
    is_success_indicator: bool = False  # 保留字段（兼容）


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
# 图片处理器（base64 编码，供 Vision API 使用）
# ============================================================================

class ImageProcessor:
    """图片处理器：将图片编码为 base64，供 GPT-4.1 Vision API 直接处理"""

    # 支持的图片格式
    SUPPORTED_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}

    # 图片大小限制（20MB，OpenAI Vision API 限制）
    MAX_FILE_SIZE = 20 * 1024 * 1024

    @staticmethod
    def encode_image(image_path: Path) -> Optional[ImageContent]:
        """将图片编码为 base64，返回 ImageContent"""
        if not image_path.exists():
            print(f"  Warning: Image not found: {image_path}")
            return None

        suffix = image_path.suffix.lower()
        if suffix not in ImageProcessor.SUPPORTED_EXTENSIONS:
            print(f"  Warning: Unsupported image format: {suffix}")
            return None

        # 检查文件大小
        file_size = image_path.stat().st_size
        if file_size > ImageProcessor.MAX_FILE_SIZE:
            print(f"  Warning: Image too large ({file_size} bytes): {image_path}")
            return None

        try:
            with open(image_path, 'rb') as f:
                image_data = f.read()

            b64_data = base64.b64encode(image_data).decode('utf-8')

            # 确定 MIME 类型
            mime_type = mimetypes.guess_type(str(image_path))[0]
            if not mime_type:
                mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg',
                           '.jpeg': 'image/jpeg', '.gif': 'image/gif',
                           '.webp': 'image/webp', '.bmp': 'image/bmp'}
                mime_type = mime_map.get(suffix, 'image/png')

            return ImageContent(
                image_path=str(image_path),
                base64_data=b64_data,
                mime_type=mime_type,
                description=f"Screenshot: {image_path.name}"
            )

        except Exception as e:
            print(f"  Warning: Failed to encode image {image_path}: {e}")
            return None


# ============================================================================
# 内容解析器
# ============================================================================

class ContentParser:
    """README 内容解析器"""

    def __init__(self, image_processor: ImageProcessor = None):
        self.image_processor = image_processor or ImageProcessor()

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

        # 提取并处理图片（base64 编码，供 Vision API 使用）
        image_paths = self.extract_images(content, cve_path)
        images = []
        for img_path in image_paths:
            image_content = self.image_processor.encode_image(img_path)
            if image_content:
                images.append(image_content)

        # 提取参考链接
        links = self.extract_reference_links(content)

        return content, code_blocks, images, links

    # ========================================================================
    # Step 0 预处理：带 ID 标注 + HTTP 请求检测 + 组装结构化输入
    # ========================================================================

    @staticmethod
    def is_http_request_block(content: str) -> bool:
        """检测代码块是否是原始 HTTP 请求"""
        first_line = content.strip().split('\n')[0].strip()
        return bool(re.match(
            r'^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+/\S*\s*(HTTP/[\d.]+)?$',
            first_line
        ))

    @staticmethod
    def is_curl_command(content: str) -> bool:
        """检测代码块是否是 curl 命令"""
        stripped = content.strip()
        return stripped.startswith('curl ') or stripped.startswith('curl\t')

    @staticmethod
    def parse_http_request_block(content: str) -> Optional[Dict[str, Any]]:
        """将原始 HTTP 请求文本解析为结构化格式"""
        lines = content.strip().split('\n')
        if not lines:
            return None

        # 解析请求行: METHOD /path HTTP/1.1
        first_line = lines[0].strip()
        req_match = re.match(r'^(GET|POST|PUT|DELETE|PATCH|HEAD|OPTIONS)\s+(\S+)', first_line)
        if not req_match:
            return None

        method = req_match.group(1)
        path = req_match.group(2)

        # 解析 headers 和 body（空行分隔）
        headers = {}
        body_lines = []
        in_body = False
        for line in lines[1:]:
            if in_body:
                body_lines.append(line)
            elif line.strip() == '':
                in_body = True
            else:
                # Header: Value
                header_match = re.match(r'^([^:]+):\s*(.*)$', line)
                if header_match:
                    headers[header_match.group(1).strip()] = header_match.group(2).strip()

        body_raw = '\n'.join(body_lines).strip() if body_lines else ""

        return {
            "method": method,
            "path": path,
            "headers": headers,
            "body_raw": body_raw
        }

    @staticmethod
    def parse_curl_command(content: str) -> Optional[Dict[str, Any]]:
        """将 curl 命令解析为结构化 HTTP 请求格式"""
        cmd = content.strip()
        # 合并续行符
        cmd = re.sub(r'\\\n\s*', ' ', cmd)

        result = {"method": "GET", "path": "", "headers": {}, "body_raw": "", "original_curl": cmd}

        # 提取 URL
        url_match = re.search(r"""(?:['"])(https?://\S+?)(?:['"])|\s(https?://\S+)""", cmd)
        if url_match:
            url = url_match.group(1) or url_match.group(2)
            # 提取 path 部分（去掉 scheme + host）
            path_match = re.match(r'https?://[^/]+(/.*)$', url)
            result["path"] = path_match.group(1) if path_match else "/"

        # 检测 method
        method_match = re.search(r'-X\s+(\w+)', cmd)
        if method_match:
            result["method"] = method_match.group(1).upper()
        elif re.search(r'--data\b|-d\s', cmd):
            result["method"] = "POST"

        # 提取 headers
        for h_match in re.finditer(r"""-H\s+'([^']+)'|-H\s+"([^"]+)" """, cmd):
            header_str = h_match.group(1) or h_match.group(2)
            if ':' in header_str:
                key, val = header_str.split(':', 1)
                result["headers"][key.strip()] = val.strip()

        # 提取 data/body（匹配配对引号）
        data_match = re.search(r"""(?:--data|--data-raw|-d)\s+'([^']*)'""", cmd, re.DOTALL)
        if not data_match:
            data_match = re.search(r'(?:--data|--data-raw|-d)\s+"([^"]*)"', cmd, re.DOTALL)
        if data_match:
            result["body_raw"] = data_match.group(1)

        # 检测特殊 curl flags
        if '--path-as-is' in cmd:
            result["curl_flags"] = ["--path-as-is"]

        return result

    def build_annotated_input(
        self,
        readme_text: str,
        code_blocks: List[CodeBlock],
        images: List[ImageContent],
        poc_files: Dict[str, str],
        docker_config: 'DockerConfig',
        cve_id: str
    ) -> Tuple[str, List[Dict]]:
        """
        组装带 ID 标注的结构化输入文档（Step 0 预处理）。

        Returns:
            (annotated_input_text, pre_parsed_requests)
        """
        parts = []
        pre_parsed_requests = []

        # === README 原文 ===
        parts.append("=== README FULL TEXT ===")
        parts.append(readme_text)
        parts.append("")

        # === 内容块清单（带 ID） ===
        parts.append("=== CONTENT BLOCKS ===")
        parts.append("")

        for i, cb in enumerate(code_blocks):
            block_id = f"CB_{i+1}"

            # 检测块类型
            if self.is_http_request_block(cb.content):
                block_type = "http_request"
                parsed = self.parse_http_request_block(cb.content)
                if parsed:
                    parsed["block_id"] = block_id
                    parsed["source_context"] = cb.context
                    pre_parsed_requests.append(parsed)
            elif self.is_curl_command(cb.content):
                block_type = "curl_command"
                parsed = self.parse_curl_command(cb.content)
                if parsed:
                    parsed["block_id"] = block_id
                    parsed["source_context"] = cb.context
                    pre_parsed_requests.append(parsed)
            elif cb.language in ('python', 'py'):
                block_type = "python"
            elif cb.language in ('bash', 'shell', 'sh'):
                block_type = "shell"
            elif cb.language in ('java', 'javascript', 'js'):
                block_type = cb.language
            else:
                block_type = cb.language or "text"

            parts.append(f"[{block_id}] ({block_type}) Line {cb.line_number} | Context: \"{cb.context}\"")
            parts.append(cb.content)
            parts.append("")

        # === 图片（实际图片通过 Vision API 传入，这里仅标注 ID） ===
        if images:
            parts.append("=== IMAGES (actual images are provided as visual input below) ===")
            parts.append("")
            for i, img in enumerate(images):
                img_id = f"IMG_{i+1}"
                parts.append(f"[{img_id}] {Path(img.image_path).name}")
                parts.append(f"  (This image is provided as visual input — analyze it directly)")
                parts.append("")

        # === 已有 PoC 文件 ===
        if poc_files:
            parts.append("=== EXISTING POC FILES IN DIRECTORY ===")
            parts.append("")
            for j, (filename, content) in enumerate(poc_files.items()):
                poc_id = f"POC_{j+1}"
                parts.append(f"[{poc_id}] {filename}")
                parts.append(content)
                parts.append("")

        # === Docker 配置 ===
        parts.append("=== DOCKER CONFIGURATION ===")
        parts.append(f"Primary Service: {docker_config.primary_service}")
        parts.append(f"Primary Port: {docker_config.primary_port}")
        if docker_config.exposed_ports:
            parts.append(f"All Exposed Ports: {docker_config.exposed_ports}")
        if docker_config.environment_vars:
            parts.append(f"Environment Variables: {json.dumps(docker_config.environment_vars)}")
        parts.append("")

        # === 预解析的 HTTP 请求 ===
        if pre_parsed_requests:
            parts.append("=== PRE-PARSED HTTP REQUESTS (auto-detected) ===")
            parts.append("")
            for req in pre_parsed_requests:
                parts.append(f"[REQ_{req['block_id']}] Method={req['method']} Path={req['path']}")
                if req.get('body_raw'):
                    parts.append(f"  Body: {req['body_raw'][:200]}{'...' if len(req.get('body_raw', '')) > 200 else ''}")
                if req.get('curl_flags'):
                    parts.append(f"  Curl Flags: {req['curl_flags']}")
                parts.append("")

        annotated_text = '\n'.join(parts)
        return annotated_text, pre_parsed_requests

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

# API 默认配置
OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.2-codex"               # completions API — 用于 PoC 生成和验证
DEFAULT_CHAT_MODEL = "gpt-5.2-2025-12-11"     # chat API (支持 Vision) — 用于 IR 提取


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

    # ========================================================================
    # Step 1 Prompt: 两层 IR 提取（事实层 + 可执行层）
    # ========================================================================

    README_ANALYSIS_PROMPT = """You are a security expert performing precise information extraction from a Vulhub CVE documentation.

## CVE ID: {cve_id}

## Input Materials (with Block IDs)

{annotated_input}

## Your Task

Extract ALL technical information needed to reproduce this exploit. Output a two-layer JSON structure:
- **Layer A (facts)**: Evidence-grounded facts only. Every claim must cite a source block ID.
- **Layer B (spec)**: Replayable specification — HTTP requests, commands, and success oracles that can be directly translated into executable code.

## CRITICAL RULES

1. **NO SPECULATION**: If the materials do not explicitly provide a version, path, parameter, request body format, or any other detail, you MUST set it to null and add the missing item to `missing_information[]`. Never guess or infer values that are not in the materials.
2. **CITE EVIDENCE**: Every key field must include `evidence[]` with the source `block` ID (e.g., "CB_2", "IMG_1", "README") and a verbatim `quote` from that source.
3. **PRESERVE EXACTLY**: HTTP paths, headers, request bodies, payloads, and URL-encoded characters (like %2e, %2f) must be copied character-for-character from the materials. Do NOT reformat, simplify, re-encode, or paraphrase any technical value.
4. **MARK VARIABLES**: Replace only obvious placeholders in the materials (such as "your-ip", "target", "your-server-ip", "localhost" used as target) with `{{{{host}}}}` and port placeholders with `{{{{port}}}}`. All other content must remain exactly as-is.

## Output JSON Structure

{{
  "facts": {{
    "cve_id": "{cve_id}",
    "service": {{
      "name": "string (e.g., Elasticsearch, Apache httpd)",
      "version": "string or null (e.g., 'before 1.2', '2.4.49')",
      "evidence": [{{"block": "string (block ID)", "quote": "string (verbatim excerpt)"}}]
    }},
    "vulnerability_type": "string (rce/sqli/ssti/path_traversal/deserialization/file_upload/auth_bypass/ssrf/xxe/xss/file_inclusion/command_injection/other)",
    "root_cause": {{
      "description": "string (one sentence explaining the root cause)",
      "evidence": [{{"block": "...", "quote": "..."}}]
    }},
    "prerequisites": [
      {{
        "description": "string (what must be true before exploitation)",
        "evidence": [{{"block": "...", "quote": "..."}}]
      }}
    ],
    "image_observations": [
      {{
        "block": "string (IMG_N)",
        "description": "string (what the screenshot shows)",
        "key_content": "string (important text visible in screenshot, e.g., 'uid=0(root)')",
        "evidence": [{{"block": "...", "quote": "..."}}]
      }}
    ],
    "reference_links": ["string (URLs from README)"],
    "missing_information": ["string (anything needed but not found in the materials)"]
  }},

  "spec": {{
    "target": {{
      "protocol": "string (http or https)",
      "default_port": {primary_port},
      "base_url": "string (e.g., 'http://{{{{host}}}}:{{{{port}}}}')"
    }},

    "requests": [
      {{
        "id": "string (REQ_1, REQ_2, ...)",
        "step": 1,
        "purpose": "string (prerequisite / exploit / verification)",
        "description": "string (what this request does)",
        "source_block": "string (CB_N that contains this request)",
        "method": "string (GET/POST/PUT/DELETE/etc.)",
        "path": "string (exact path from materials, with {{{{host}}}}/{{{{port}}}} variables only)",
        "headers": {{"string": "string (exact header values)"}},
        "body_raw": "string (exact request body, with {{{{host}}}}/{{{{port}}}} variables only) or empty string",
        "content_type": "string or null (Content-Type header value)",
        "variables": ["string (list of variables used, e.g., '{{{{host}}}}', '{{{{port}}}}')"],
        "evidence": [{{"block": "...", "quote": "..."}}]
      }}
    ],

    "oracles": [
      {{
        "id": "string (ORC_1, ORC_2, ...)",
        "type": "string (response_contains / status_code / regex / exit_code)",
        "applies_to": "string (REQ_N that this oracle checks)",
        "expected_strings": ["string (substrings to look for in response)"],
        "expected_status": null,
        "evidence": [{{"block": "...", "quote": "..."}}]
      }}
    ],

    "attack_sequence_summary": [
      "string (step 1: brief description)",
      "string (step 2: brief description)"
    ],

    "dependencies": ["string (pip package names ONLY, e.g., 'requests'. Do NOT include stdlib modules)"]
  }}
}}

Output ONLY valid JSON. No text before or after."""

    # ========================================================================
    # Step 2 Prompt: 回放式 PoC 生成
    # ========================================================================

    POC_GENERATION_PROMPT = """You are a security expert generating a Python PoC script for a CVE.

## CVE ID: {cve_id}

## Replayable Specification (from analysis):
{ir_spec}

## README Original Text (for cross-reference):
{readme_content}

## Existing PoC Reference (if available):
{existing_poc}

## All Code Blocks from README:
{all_code_blocks}

## Execution Environment
This PoC will run inside a Docker attacker container on the same network as the target:
- Target is accessible at the hostname and port passed via --host and --port arguments
  (e.g., {service_name}:{primary_port} inside Docker network)
- Python 3 + requests are pre-installed
- Direct TCP access to target (no firewall)

## YOUR TASK

根据 Replayable Specification、README 原文、已有 PoC 参考和代码块，
生成一个完整的、可执行的 Python PoC 脚本。

### 注意事项（Notes）：

- spec.requests[] 提供了攻击的核心请求，作为重要参考。但 spec 可能不完整，
  你需要根据 README 和目标服务的特性，自行判断是否需要补充前置步骤
  （如登录、session 建立、token 获取等）

- 仔细阅读 README 原文和截图描述，它们包含了 spec 可能遗漏的关键上下文
  （如 Web 界面的交互流程、认证方式、具体的 URL 路径等）

- 如果有已有 PoC 参考（Existing PoC Reference），认真分析其实现思路，
  它可能包含正确的请求流程和参数

- 实现 spec.oracles[] 中的验证逻辑：
  - response_contains → 检查 response.text 是否包含 expected_strings
  - status_code → 检查 response.status_code
  - regex → 使用 re.search 匹配 response.text
  - exit_code → 检查进程返回码

- 目标在 Docker 网络中，通过 --host 和 --port 参数访问

- 每个 HTTP 请求后必须打印调试信息：
  print(f"[DEBUG] Status: {{resp.status_code}}")
  print(f"[DEBUG] Response (first 1000 chars): {{resp.text[:1000]}}")

- 脚本要求：
  - 以 #!/usr/bin/env python3 开头
  - argparse：--host (required), --port (default={primary_port})
  - 输出标记：[+] 成功, [-] 失败, [*] 信息
  - exit code：0 成功, 1 失败

## Output
Generate ONLY the complete Python script. No explanations before or after.
Start with #!/usr/bin/env python3"""

    # ========================================================================
    # Step 3 Prompt: 逐项对账验证
    # ========================================================================

    POC_VALIDATION_PROMPT = """You are a security expert performing item-by-item verification of a generated PoC script against its specification.

## Replayable Specification:
{ir_spec}

## README Original Text (for cross-reference):
{readme_content}

## Generated PoC Script:
```python
{generated_poc}
```

## YOUR TASK: Verify the PoC by comparing it against the spec, item by item.

### Verification Dimensions:

1. **request_diff[]** — For EACH request in spec.requests[]:
   - Is the HTTP method identical? (e.g., POST vs GET)
   - Is the path character-for-character identical? (pay special attention to URL-encoded chars like %2e, %2f, query parameters)
   - Are critical headers present and correct? (especially Content-Type)
   - Is the request body character-for-character identical to spec.body_raw? (check JSON structure, escaping, field names, payload strings)
   - Status: "match" / "mismatch" / "missing"
   - If mismatch: specify the exact field, expected value (from spec), and actual value (from PoC)

2. **oracle_coverage[]** — For EACH oracle in spec.oracles[]:
   - Does the PoC script implement this success check?
   - Is the check logic correct? (correct string to search for, correct response to check)
   - Status: "covered" / "not_covered" / "incorrect"

3. **parameterization** — Variable handling:
   - Are --host and --port correctly wired to all requests?
   - Are there any hardcoded target addresses (e.g., "localhost", "127.0.0.1", "your-ip")?

4. **execution_readiness** — Can the script actually run?
   - Is the Python syntax valid?
   - Are all imports present?
   - Are argparse arguments correctly defined?
   - Are request prerequisite steps executed before exploit steps?

## Output JSON:
{{
  "verdict": "pass or fail",
  "request_diff": [
    {{
      "spec_request": "string (REQ_N)",
      "status": "match or mismatch or missing",
      "details": null or {{
        "field": "string (method/path/headers/body)",
        "expected": "string (from spec)",
        "actual": "string (from PoC)",
        "fix": "string (exact code fix)"
      }}
    }}
  ],
  "oracle_coverage": [
    {{
      "oracle": "string (ORC_N)",
      "status": "covered or not_covered or incorrect",
      "details": null or "string (what is wrong)"
    }}
  ],
  "parameterization": {{
    "host_correct": true or false,
    "port_correct": true or false,
    "hardcoded_addresses": ["string (any hardcoded addresses found)"]
  }},
  "execution_readiness": {{
    "syntax_valid": true or false,
    "imports_complete": true or false,
    "argparse_correct": true or false,
    "prerequisite_order_correct": true or false
  }},
  "issues": [
    {{
      "severity": "critical or minor",
      "spec_ref": "string (REQ_N or ORC_N or null)",
      "location": "string (e.g., 'line 42' or 'exploit() function')",
      "wrong_code": "string (the exact code that is wrong)",
      "fix": "string (the exact corrected code)",
      "reason": "string (why it is wrong, referencing spec)"
    }}
  ],
  "summary": "string (one sentence: why it passes or what is the most critical problem)"
}}

Output ONLY valid JSON. No text before or after."""

    def __init__(self, api_key: str = None, model: str = None,
                 api_base: str = None, chat_model: str = None):
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        api_base = api_base or os.getenv("OPENAI_API_BASE") or OPENAI_BASE_URL
        self.client = OpenAI(api_key=api_key, base_url=api_base)
        self.model = model or DEFAULT_MODEL              # completions 模型（PoC 生成）
        self.chat_model = chat_model or DEFAULT_CHAT_MODEL  # chat 模型（IR 提取，支持 Vision）

    def analyze_readme(self, entry: VulhubEntry, annotated_input: str) -> Dict:
        """
        Step 1: 两层 IR 提取（事实层 + 可执行层）。
        使用 chat_model (Vision API) 直接处理 README 中的截图。

        Args:
            entry: VulhubEntry with parsed README data
            annotated_input: Pre-processed annotated input from build_annotated_input()

        Returns:
            Two-layer IR dict with 'facts' and 'spec' keys
        """
        prompt = self.README_ANALYSIS_PROMPT.format(
            annotated_input=annotated_input,
            primary_port=entry.docker_config.primary_port,
            cve_id=entry.cve_id
        )

        # 构建 Responses API 输入（文本 + 图片）— 使用 chat_model (支持 Vision)
        user_content = [{"type": "input_text", "text": prompt}]

        # 将图片作为 Vision 输入附加
        for i, img in enumerate(entry.readme_analysis.images):
            if img.base64_data:
                img_id = f"IMG_{i+1}"
                user_content.append({
                    "type": "input_text",
                    "text": f"\n[{img_id}] Screenshot from README ({Path(img.image_path).name}):"
                })
                user_content.append({
                    "type": "input_image",
                    "image_url": f"data:{img.mime_type};base64,{img.base64_data}"
                })

        try:
            response = self.client.responses.create(
                model=self.chat_model,
                instructions="You are a security expert performing precise information extraction. You MUST output ONLY valid JSON with the exact structure requested. No explanations, no markdown, no extra text.",
                input=[{"role": "user", "content": user_content}],
                temperature=0.1
            )

            ir = parse_json_response(response.output_text)

            # 确保顶层结构存在
            if 'facts' not in ir:
                ir = {"facts": ir, "spec": {"target": {}, "requests": [], "oracles": [], "dependencies": ["requests"]}}
            if 'spec' not in ir:
                ir['spec'] = {"target": {}, "requests": [], "oracles": [], "dependencies": ["requests"]}

            return ir
        except Exception as e:
            print(f"  Warning: README analysis failed: {e}")
            return {
                "facts": {
                    "cve_id": entry.cve_id,
                    "service": {"name": entry.docker_config.primary_service, "version": None, "evidence": []},
                    "vulnerability_type": "other",
                    "root_cause": {"description": "", "evidence": []},
                    "prerequisites": [],
                    "image_observations": [],
                    "reference_links": [],
                    "missing_information": ["README analysis failed"]
                },
                "spec": {
                    "target": {"protocol": "http", "default_port": entry.docker_config.primary_port, "base_url": f"http://{{{{host}}}}:{{{{port}}}}"},
                    "requests": [],
                    "oracles": [],
                    "attack_sequence_summary": [],
                    "dependencies": ["requests"]
                }
            }

    def generate_poc(self, entry: VulhubEntry, ir: Dict, feedback: str = None) -> GeneratedPoC:
        """
        Step 2: 回放式 PoC 生成。

        Args:
            entry: VulhubEntry with parsed README data
            ir: Two-layer IR from analyze_readme()
            feedback: Feedback from validation/Docker failure (optional)

        Returns:
            GeneratedPoC with the generated script
        """
        # 准备现有 PoC 参考
        existing_poc = ""
        if entry.original_poc_files:
            if 'poc.py' in entry.original_poc_files:
                existing_poc = entry.original_poc_files['poc.py']
            else:
                existing_poc = list(entry.original_poc_files.values())[0]

        # 准备所有代码块（不再过滤语言）
        all_code_blocks_text = ""
        for i, cb in enumerate(entry.readme_analysis.code_blocks):
            block_id = f"CB_{i+1}"
            all_code_blocks_text += f"\n[{block_id}] ({cb.language}) Context: \"{cb.context}\"\n"
            all_code_blocks_text += f"{cb.content}\n"

        # 从 IR 中提取信息
        facts = ir.get('facts', {})
        spec = ir.get('spec', {})
        service_name = facts.get('service', {}).get('name', entry.docker_config.primary_service)
        primary_port = spec.get('target', {}).get('default_port', entry.docker_config.primary_port)

        # 从 spec 提取依赖
        deps = spec.get('dependencies', ['requests'])

        # 提取 success indicators（从 oracles）
        success_indicators = []
        for oracle in spec.get('oracles', []):
            for s in oracle.get('expected_strings', []):
                success_indicators.append(s)

        prompt = self.POC_GENERATION_PROMPT.format(
            ir_spec=json.dumps(ir, indent=2, ensure_ascii=False),
            readme_content=entry.readme_analysis.raw_text,
            existing_poc=existing_poc or "No existing PoC available",
            all_code_blocks=all_code_blocks_text or "No code blocks found",
            cve_id=entry.cve_id,
            service_name=service_name,
            primary_port=primary_port
        )

        if feedback:
            prompt += f"\n\n## Previous Issues (MUST FIX):\n{feedback}"

        try:
            response = self.client.responses.create(
                model=self.model,
                instructions="You are a security expert translating a replayable specification into Python exploit code. Replay requests exactly from the spec. Output only the Python script, nothing else.",
                input=prompt
            )

            script = response.output_text.strip()

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
                dependencies=deps,
                execution_cmd=f"python3 poc.py --host {{host}} --port {primary_port}",
                expected_output=', '.join(success_indicators),
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
    """PoC 脚本验证器（逐项对账验证）"""

    MAX_RETRIES = 3

    def __init__(self, api_key: str = None, model: str = None,
                 api_base: str = None):
        api_key = api_key or os.getenv("OPENAI_API_KEY")
        api_base = api_base or os.getenv("OPENAI_API_BASE") or OPENAI_BASE_URL
        self.client = OpenAI(api_key=api_key, base_url=api_base)
        self.model = model or DEFAULT_MODEL

    def validate(self, entry: VulhubEntry, ir: Dict) -> ValidationResult:
        """
        Step 3: 逐项对账验证 PoC 与 IR spec 的一致性。

        Args:
            entry: VulhubEntry with poc_script set
            ir: Two-layer IR from analyze_readme()

        Returns:
            ValidationResult with verdict and detailed issues
        """
        if not entry.poc_script or entry.poc_script.script == "# Generation failed":
            return ValidationResult(
                is_valid=False,
                issues=[{"severity": "critical", "reason": "No PoC script generated", "fix": "Regenerate"}],
                missing_steps=[],
                summary="No valid PoC script to validate"
            )

        prompt = PoCGenerator.POC_VALIDATION_PROMPT.format(
            ir_spec=json.dumps(ir, indent=2, ensure_ascii=False),
            readme_content=entry.readme_analysis.raw_text,
            generated_poc=entry.poc_script.script
        )

        try:
            response = self.client.responses.create(
                model=self.model,
                instructions="You are a security expert performing item-by-item verification. Compare the PoC script against the specification. You MUST output ONLY valid JSON.",
                input=prompt
            )

            result = parse_json_response(response.output_text)

            # 从新格式提取 is_valid
            verdict = result.get('verdict', 'fail')
            is_valid = verdict == 'pass'

            # 合并所有问题源
            issues = result.get('issues', [])

            # 从 request_diff 中提取 mismatch 问题
            for rd in result.get('request_diff', []):
                if rd.get('status') in ('mismatch', 'missing'):
                    details = rd.get('details') or {}
                    issues.append({
                        "severity": "critical",
                        "spec_ref": rd.get('spec_request', ''),
                        "location": f"request {rd.get('spec_request', '')}",
                        "wrong_code": details.get('actual', ''),
                        "fix": details.get('fix', f"Match spec: {details.get('expected', '')}"),
                        "reason": f"Field '{details.get('field', 'unknown')}' does not match spec. Expected: {details.get('expected', '')}"
                    })

            # 从 oracle_coverage 中提取未覆盖问题
            missing_steps = []
            for oc in result.get('oracle_coverage', []):
                if oc.get('status') in ('not_covered', 'incorrect'):
                    missing_steps.append(f"Oracle {oc.get('oracle', '')}: {oc.get('details', 'not implemented')}")

            return ValidationResult(
                is_valid=is_valid,
                issues=issues,
                missing_steps=missing_steps,
                summary=result.get('summary', '')
            )

        except Exception as e:
            print(f"  Warning: LLM validation failed: {e}")
            return ValidationResult(
                is_valid=False,
                issues=[{"severity": "critical", "reason": f"Validation error: {e}", "fix": "Retry"}],
                missing_steps=[],
                summary=f"LLM validation error: {e}"
            )

    def build_feedback(self, validation: ValidationResult) -> str:
        """将逐项对账发现的问题格式化为反馈文本"""
        feedback_parts = []

        if validation.issues:
            feedback_parts.append("## Issues found by spec-based verification (MUST FIX ALL):\n")
            for i, issue in enumerate(validation.issues, 1):
                severity = issue.get('severity', 'unknown')
                feedback_parts.append(f"### Issue {i} [{severity.upper()}]:")
                if issue.get('spec_ref'):
                    feedback_parts.append(f"Spec reference: {issue['spec_ref']}")
                if issue.get('location'):
                    feedback_parts.append(f"Location: {issue['location']}")
                if issue.get('wrong_code'):
                    feedback_parts.append(f"Wrong code: `{issue['wrong_code']}`")
                if issue.get('reason'):
                    feedback_parts.append(f"Reason: {issue['reason']}")
                if issue.get('fix'):
                    feedback_parts.append(f"Fix: `{issue['fix']}`")
                feedback_parts.append("")

        if validation.missing_steps:
            feedback_parts.append("## Uncovered oracles / missing steps:")
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

    @staticmethod
    def _scan_poc_imports(poc_script: str) -> List[str]:
        """从 PoC 代码中扫描 import 语句，提取第三方依赖包名。

        解析 `import xxx` 和 `from xxx import yyy` 两种形式，
        过滤掉标准库模块，返回需要 pip install 的包名列表。
        """
        stdlib = {
            "argparse", "os", "sys", "json", "re", "time", "hashlib",
            "base64", "urllib", "socket", "struct", "io", "string",
            "collections", "itertools", "functools", "pathlib",
            "subprocess", "threading", "http", "html", "xml", "csv",
            "math", "random", "datetime", "copy", "textwrap", "logging",
            "traceback", "ssl", "binascii", "codecs", "gzip", "zlib",
            "shutil", "tempfile", "glob", "fnmatch", "stat", "errno",
            "signal", "abc", "contextlib", "typing", "enum", "dataclasses",
            "unittest", "pprint", "inspect", "operator", "warnings",
            "multiprocessing", "concurrent", "asyncio", "selectors",
            "configparser", "secrets", "hmac", "uuid", "platform",
            "ctypes", "array", "queue", "heapq", "bisect",
            "urllib3",  # bundled with requests
        }
        # import name → pip package name (common mismatches)
        import_to_pip = {
            "bs4": "beautifulsoup4",
            "cv2": "opencv-python",
            "PIL": "Pillow",
            "yaml": "PyYAML",
            "Crypto": "pycryptodome",
            "jwt": "PyJWT",
            "lxml": "lxml",
            "paramiko": "paramiko",
            "socks": "PySocks",
        }
        deps = set()
        for line in poc_script.splitlines():
            line = line.strip()
            # import xxx / import xxx, yyy
            m = re.match(r'^import\s+([\w,\s]+)', line)
            if m:
                for mod in m.group(1).split(','):
                    top = mod.strip().split('.')[0]
                    if top and top not in stdlib:
                        deps.add(import_to_pip.get(top, top))
            # from xxx import yyy
            m = re.match(r'^from\s+([\w.]+)\s+import', line)
            if m:
                top = m.group(1).split('.')[0]
                if top and top not in stdlib:
                    deps.add(import_to_pip.get(top, top))
        return list(deps)

    def verify(self, entry: VulhubEntry, poc_script: str, ir: Dict) -> DockerVerificationResult:
        """
        主验证方法：启动 Docker 环境 → 执行 PoC → 分析结果 → 清理

        Args:
            entry: VulhubEntry
            poc_script: PoC script text
            ir: Two-layer IR dict (with 'facts' and 'spec' keys)
        """
        compose_path = Path(entry.docker_config.compose_path)
        sanitized_id = re.sub(r'[^a-z0-9]', '', entry.cve_id.lower())
        project_name = f"vulpoc-{sanitized_id}-{int(time.time()) % 100000}"

        target_host = entry.docker_config.primary_service
        target_port = entry.docker_config.primary_port

        # 从 IR 提取 success_indicators 和 dependencies
        spec = ir.get('spec', {})
        success_indicators = []
        for oracle in spec.get('oracles', []):
            for s in oracle.get('expected_strings', []):
                success_indicators.append(s)
        poc_deps = spec.get('dependencies', [])
        # 从 PoC 代码本身扫描 import，补全 spec 遗漏的依赖
        scanned_deps = self._scan_poc_imports(poc_script)
        if scanned_deps:
            poc_deps = list(set(poc_deps + scanned_deps))

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

            # 失败时打印 stderr/stdout 供诊断
            if not is_success:
                if stderr.strip():
                    # 截取最后 800 字符（通常包含完整 traceback）
                    stderr_preview = stderr.strip()[-800:]
                    print(f"      [Docker] stderr:\n{stderr_preview}")
                if stdout.strip():
                    stdout_preview = stdout.strip()[-400:]
                    print(f"      [Docker] stdout:\n{stdout_preview}")
                if not stderr.strip() and not stdout.strip():
                    print(f"      [Docker] (no output - script produced nothing)")

            return DockerVerificationResult(
                success=is_success,
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
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

    def build_feedback(self, result: DockerVerificationResult, poc_code: str = "",
                       attempt_num: int = 1, previous_feedbacks: list = None) -> str:
        """将 Docker 验证结果格式化为反馈文本，供 PoCGenerator 重新生成。

        不做 rule-based 诊断，完整呈现所有信息，让 LLM 自主分析。
        """
        parts = ["## Docker Execution Feedback (attempt {}/{})".format(
            attempt_num, DockerPoCVerifier.DOCKER_MAX_RETRIES)]

        # 1. 上一次 PoC 完整代码
        if poc_code:
            parts.append(f"\n### Your Previous PoC Code:\n```python\n{poc_code}\n```")

        # 2. 完整 stdout
        if result.stdout:
            parts.append(f"\n### stdout:\n```\n{result.stdout}\n```")
        else:
            parts.append("\n### stdout: (empty)")

        # 3. 完整 stderr
        if result.stderr:
            parts.append(f"\n### stderr:\n```\n{result.stderr}\n```")
        else:
            parts.append("\n### stderr: (empty)")

        # 4. 执行元信息
        parts.append(
            f"\n### Execution Info:\n"
            f"- exit_code: {result.exit_code}\n"
            f"- execution_time: {result.execution_time:.1f}s\n"
            f"- indicators_matched: {result.indicators_matched if result.indicators_matched else 'none'}"
        )

        # 5. 历史累积（前几次尝试的摘要）
        if previous_feedbacks:
            parts.append("\n### Previous Attempts Summary:")
            for i, fb in enumerate(previous_feedbacks, 1):
                parts.append(f"\n**Attempt {i}** (exit_code={fb['exit_code']}):")
                if fb.get('stdout'):
                    stdout_summary = fb['stdout'][:500]
                    parts.append(f"stdout (first 500 chars): {stdout_summary}")
                if fb.get('stderr'):
                    stderr_summary = fb['stderr'][:500]
                    parts.append(f"stderr (first 500 chars): {stderr_summary}")

        # 6. 一句话要求
        parts.append(
            "\n### 要求:\n"
            "分析上述执行结果，找出问题所在，生成修复后的 PoC。"
            "如果这不是第一次尝试，你必须采取与之前不同的策略。"
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
        # """从路径提取 CVE ID"""
        # match = re.search(r'(CVE-\d{4}-\d+)', str(cve_path), re.IGNORECASE)
        # if match:
        #     return match.group(1).upper()
        """Extract CVE ID in category/id format (e.g., apache/CVE-2021-41773)"""
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

        self.image_processor = ImageProcessor()
        self.content_parser = ContentParser(self.image_processor)
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
        """处理单个 CVE（IR 中间表示 + 回放式生成流水线）"""
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

        # ================================================================
        # Step 0: 预处理 — 带 ID 标注 + HTTP 请求检测
        # ================================================================
        print(f"    Step 0: Preprocessing (block IDs, HTTP detection)...")
        annotated_input, pre_parsed_requests = self.content_parser.build_annotated_input(
            readme_text=readme_text,
            code_blocks=code_blocks,
            images=images,
            poc_files=original_poc_files,
            docker_config=docker_config,
            cve_id=cve_id
        )
        print(f"    Detected {len(pre_parsed_requests)} HTTP request blocks")

        # ================================================================
        # Step 1: 两层 IR 提取（事实层 + 可执行层）
        # ================================================================
        print(f"    Step 1: Extracting IR (facts + replayable spec)...")
        ir = self.poc_generator.analyze_readme(entry, annotated_input)

        # 从 IR facts 更新 entry 元数据
        facts = ir.get('facts', {})
        service_info = facts.get('service', {})
        entry.readme_analysis.vulnerability_type = facts.get('vulnerability_type', 'other')
        entry.readme_analysis.service_name = service_info.get('name', '')
        entry.readme_analysis.service_version = service_info.get('version', '') or ''
        root_cause = facts.get('root_cause', {})
        entry.readme_analysis.vulnerability_description = root_cause.get('description', '')

        # 从 IR spec 更新
        spec = ir.get('spec', {})
        entry.readme_analysis.exploitation_steps = spec.get('attack_sequence_summary', [])
        # 从 oracles 提取 success indicators
        success_indicators = []
        for oracle in spec.get('oracles', []):
            for s in oracle.get('expected_strings', []):
                success_indicators.append(s)
        entry.readme_analysis.success_indicators = success_indicators

        num_requests = len(spec.get('requests', []))
        num_oracles = len(spec.get('oracles', []))
        print(f"    Type: {entry.readme_analysis.vulnerability_type}")
        print(f"    Service: {entry.readme_analysis.service_name}")
        print(f"    Spec: {num_requests} requests, {num_oracles} oracles")
        if facts.get('missing_information'):
            print(f"    Missing info: {facts['missing_information']}")

        # ================================================================
        # Step 2: 回放式 PoC 生成
        # ================================================================
        print(f"    Step 2: Generating PoC (replay-based)...")
        poc = self.poc_generator.generate_poc(entry, ir)

        if poc.validation_status == "failed":
            print(f"    PoC generation failed")
            entry.poc_script = poc
            return entry

        # ================================================================
        # Step 3: 逐项对账验证循环
        # ================================================================
        entry.poc_script = poc

        # 判断 spec 是否足够完整来做有意义的对账
        missing_info = ir.get('facts', {}).get('missing_information', [])
        spec_requests = ir.get('spec', {}).get('requests', [])
        spec_incomplete = len(missing_info) >= 3 or len(spec_requests) == 0

        if spec_incomplete:
            # Spec 缺失太多信息，LLM 对账必然失败（PoC 必须填补 spec 没有的细节）
            # 跳过 LLM 验证，直接进 Docker 验证（最终判定标准）
            print(f"    Step 3: Skipped (spec has {len(missing_info)} missing items, "
                  f"{len(spec_requests)} requests — too incomplete for meaningful diff)")
            entry.poc_script.validation_status = "spec_incomplete"
            entry.poc_script.validation_notes = f"Spec too incomplete ({len(missing_info)} missing items), skipping LLM verification"
        else:
            print(f"    Step 3: Spec-based verification...")
            for llm_attempt in range(PoCValidator.MAX_RETRIES):
                validation = self.poc_validator.validate(entry, ir)
                entry.poc_script.llm_attempts = llm_attempt + 1

                if validation.is_valid:
                    entry.poc_script.validation_status = "llm_passed"
                    entry.poc_script.validation_notes = validation.summary
                    print(f"    Verification PASSED (attempt {llm_attempt + 1})")
                    break

                # 对账发现问题 → 用反馈修正后再验证
                print(f"    Verification found issues (attempt {llm_attempt + 1}): {validation.summary}")
                feedback = self.poc_validator.build_feedback(validation)
                poc = self.poc_generator.generate_poc(entry, ir, feedback)
                entry.poc_script = poc
            else:
                # 验证多次仍有问题，标记但仍继续送 Docker 验证
                entry.poc_script.validation_status = "llm_failed"
                entry.poc_script.validation_notes = f"Spec verification failed after {PoCValidator.MAX_RETRIES} attempts: {validation.summary}"
                print(f"    Spec verification exhausted, proceeding to Docker anyway")

        # ================================================================
        # Step 4-6: Docker 实战验证循环（最终判定）
        # ================================================================
        if self.docker_verifier and entry.poc_script.validation_status != "failed":
            print(f"    Step 4-6: Docker verification...")
            docker_verified = False

            docker_feedback_history = []  # 累积每次尝试的摘要

            for docker_attempt in range(DockerPoCVerifier.DOCKER_MAX_RETRIES):
                print(f"    Docker attempt {docker_attempt + 1}/{DockerPoCVerifier.DOCKER_MAX_RETRIES}...")
                current_poc_code = entry.poc_script.script
                docker_result = self.docker_verifier.verify(
                    entry, current_poc_code, ir
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

                # 保存本次尝试摘要到历史
                docker_feedback_history.append({
                    'exit_code': docker_result.exit_code,
                    'stdout': docker_result.stdout,
                    'stderr': docker_result.stderr,
                })

                # 用完整信息（含 PoC 代码和历史）重新生成
                docker_feedback = self.docker_verifier.build_feedback(
                    docker_result,
                    poc_code=current_poc_code,
                    attempt_num=docker_attempt + 1,
                    previous_feedbacks=docker_feedback_history[:-1] if len(docker_feedback_history) > 1 else None,
                )
                print(f"    Docker failed, regenerating with real error feedback...")
                poc = self.poc_generator.generate_poc(entry, ir, docker_feedback)
                entry.poc_script = poc

            # 保存验证通过的 PoC 到 sample 目录
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

                # 图片元数据（不含 base64 数据，避免 parquet 过大）
                "image_info": json.dumps([
                    {"image_path": img.image_path, "description": img.description}
                    for img in entry.readme_analysis.images
                ], ensure_ascii=False),

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
  # Process all CVEs with OpenAI gpt-5.2-codex (default)
  python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ~/data/cve_vulhub

  # Process first 10 CVEs (for testing)
  python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ~/data/cve_vulhub --limit 10

  # LLM-only mode (no Docker verification)
  python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ~/data/cve_vulhub --no-docker

  # Incremental run: skip already verified samples
  python vulhub_dataset_builder.py --vulhub_path ~/vulhub --output_dir ~/data/cve_vulhub --skip-verified

  # Use custom models
  python vulhub_dataset_builder.py --model gpt-5.2-codex --chat_model gpt-5.2-2025-12-11

  # Use a different OpenAI-compatible API
  python vulhub_dataset_builder.py --api_base https://custom-api.example.com/v1 --model custom-model --api_key sk-xxx
"""
    )
    parser.add_argument("--vulhub_path", type=str, default="~/vulhub",
                        help="Path to Vulhub repository (default: ~/vulhub)")
    parser.add_argument("--output_dir", type=str, default="~/data/cve_vulhub",
                        help="Output directory for dataset (default: ~/data/cve_vulhub)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of CVEs to process (for testing)")
    parser.add_argument("--model", type=str, default=None,
                        help=f"Completions model for PoC generation/validation (default: {DEFAULT_MODEL})")
    parser.add_argument("--chat_model", type=str, default=None,
                        help=f"Chat model for IR extraction with Vision (default: {DEFAULT_CHAT_MODEL})")
    parser.add_argument("--api_key", type=str, default=None,
                        help="API key (default: from OPENAI_API_KEY env)")
    parser.add_argument("--api_base", type=str, default=None,
                        help=f"API base URL (default: OPENAI_API_BASE env or {OPENAI_BASE_URL})")
    parser.add_argument("--no-docker", action="store_true",
                        help="Disable Docker verification (LLM-only mode)")
    parser.add_argument("--skip-verified", action="store_true",
                        help="Skip CVEs that already have poc_verified.py")

    args = parser.parse_args()

    # 解析 API 配置
    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    api_base = args.api_base or os.getenv("OPENAI_API_BASE") or OPENAI_BASE_URL
    model = args.model or DEFAULT_MODEL
    chat_model = args.chat_model or DEFAULT_CHAT_MODEL

    print("=" * 60)
    print("Vulhub Dataset Builder v2.0")
    print("=" * 60)
    print(f"Vulhub path: {args.vulhub_path}")
    print(f"Output dir: {args.output_dir}")
    print(f"API base: {api_base}")
    print(f"Completions model (PoC gen/validation): {model}")
    print(f"Chat model (IR extraction + Vision): {chat_model}")
    print(f"Docker verification: {'disabled' if args.no_docker else 'enabled'}")
    print(f"Skip verified: {args.skip_verified}")
    if args.limit:
        print(f"Limit: {args.limit}")
    print("=" * 60)

    # 检查 API key
    if not api_key:
        print("Error: API key not found. Set OPENAI_API_KEY environment variable or use --api_key")
        return 1

    try:
        # 初始化
        scanner = VulhubScanner(args.vulhub_path)
        builder = DatasetBuilder(args.output_dir, api_key=api_key,
                                 api_base=api_base, no_docker=args.no_docker)

        # 更新模型设置
        builder.poc_generator.model = model
        builder.poc_generator.chat_model = chat_model
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
