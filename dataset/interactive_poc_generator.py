"""
Interactive PoC Generation Pipeline v2.0
LLM Agent 在 Docker 环境中边交互边生成 PoC，替代盲生成模式。

核心特性：
1. Agent 读 README 后直接在 Docker 环境中交互式探索
2. 实时观察攻击结果，迭代修正
3. 输出 poc.py + verify.py + requirements.txt 到文件夹结构
4. 仅做生成，验证作为独立步骤在之后统一进行
"""

import io
import json
import os
import random
import re
import shlex
import shutil
import subprocess
import tarfile
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

import docker
from openai import OpenAI

# 从现有模块复用组件
from vulhub_dataset_builder import (
    ContentParser,
    ImageProcessor,
    VulhubScanner,
    CodeBlock,
    ImageContent,
    DockerConfig,
    parse_json_response,
)

# ============================================================================

# 默认配置source .venv/bin/activate
# ============================================================================

OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_MODEL = "gpt-5.2"
MAX_AGENT_STEPS = 30

# ============================================================================
# 数据类
# ============================================================================


@dataclass
class AgentAction:
    """Agent 单步操作记录"""
    step: int
    tool_name: str
    tool_input: Dict[str, Any]
    tool_output: str
    timestamp: str


@dataclass
class AgentOutput:
    """Agent 运行输出"""
    poc_script: str = ""
    verify_script: str = ""
    requirements: List[str] = field(default_factory=list)
    conversation: List[Dict] = field(default_factory=list)
    actions_log: List[AgentAction] = field(default_factory=list)
    finished: bool = False
    steps_used: int = 0


@dataclass
class PoCBundle:
    """PoC 产物包"""
    poc_script: str
    verify_script: str
    requirements: List[str]


@dataclass
class VerificationResult:
    """验证结果"""
    poc_exit_code: int
    poc_stdout: str
    poc_stderr: str
    verify_exit_code: int
    verify_stdout: str
    verify_stderr: str
    success: bool



# ============================================================================
# 工具函数
# ============================================================================


def scan_poc_imports(poc_script: str) -> List[str]:
    """从 PoC 代码中扫描 import 语句，提取第三方依赖包名。

    复用自 DockerPoCVerifier._scan_poc_imports()
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
        "urllib3",
    }
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
        m = re.match(r'^import\s+([\w,\s]+)', line)
        if m:
            for mod in m.group(1).split(','):
                top = mod.strip().split('.')[0]
                if top and top not in stdlib:
                    deps.add(import_to_pip.get(top, top))
        m = re.match(r'^from\s+([\w.]+)\s+import', line)
        if m:
            top = m.group(1).split('.')[0]
            if top and top not in stdlib:
                deps.add(import_to_pip.get(top, top))
    return list(deps)


def detect_compose_command() -> List[str]:
    """检测可用的 docker compose 命令"""
    try:
        subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True, check=True, timeout=10
        )
        return ["docker", "compose"]
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        pass
    if shutil.which("docker-compose"):
        return ["docker-compose"]
    raise RuntimeError("Neither 'docker compose' nor 'docker-compose' found")


# ============================================================================
# DockerEnvironment — Docker 生命周期管理
# ============================================================================


class DockerEnvironment:
    """Docker 环境管理器：启动 Vulhub 环境 + attacker 容器。

    封装自 DockerPoCVerifier 的核心方法，提供通用命令执行能力。
    """

    ATTACKER_IMAGE = "cve-attacker:latest"

    def __init__(self, poc_timeout: int = 60, service_wait: int = 60):
        self.poc_timeout = poc_timeout
        self.service_wait = service_wait
        self.docker_client = docker.from_env()
        self.compose_cmd = detect_compose_command()

        # 运行状态
        self.project_name: Optional[str] = None
        self.compose_path: Optional[Path] = None
        self.network_name: Optional[str] = None
        self.attacker = None
        self.target_host: Optional[str] = None
        self.target_port: Optional[int] = None
        self._started = False

    def start(self, cve_dir: Path, docker_config: DockerConfig,
              extra_deps: Optional[List[str]] = None) -> bool:
        """启动 Vulhub 环境 + attacker 容器。

        Args:
            cve_dir: CVE 目录路径（含 docker-compose.yml）
            docker_config: Docker 配置
            extra_deps: 额外的 pip 依赖

        Returns:
            True if started successfully
        """
        self.compose_path = Path(docker_config.compose_path)
        self.target_host = docker_config.primary_service
        self.target_port = docker_config.primary_port

        sanitized_id = re.sub(r'[^a-z0-9]', '', cve_dir.name.lower())
        self.project_name = f"vulpoc-{sanitized_id}-{int(time.time()) % 100000}"

        # Step 1: 启动漏洞环境
        print(f"    [Docker] Starting environment ({cve_dir.name})...")
        self.network_name = self._start_environment()
        if not self.network_name:
            return False

        # Step 2: 创建 attacker 容器
        print(f"    [Docker] Creating attacker container...")
        deps = list(set(["requests"] + (extra_deps or [])))
        self.attacker = self._create_attacker(deps)

        # Step 3: 等待目标服务就绪
        print(f"    [Docker] Waiting for {self.target_host}:{self.target_port}...")
        ready = self._wait_for_service()
        if not ready:
            print(f"    [Docker] Service not ready after {self.service_wait}s")
            return False

        self._started = True
        print(f"    [Docker] Environment ready")
        return True

    def _start_environment(self) -> Optional[str]:
        """启动 docker-compose 环境，返回网络名"""
        compose_dir = self.compose_path.parent
        try:
            cmd = self.compose_cmd + [
                "-f", str(self.compose_path),
                "-p", self.project_name,
                "up", "-d"
            ]
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=120, cwd=str(compose_dir)
            )
            # docker compose 可能因 deprecation warning 返回非零码，改为检查容器是否实际创建
            if result.returncode != 0:
                containers = self.docker_client.containers.list(
                    filters={"label": f"com.docker.compose.project={self.project_name}"}
                )
                if not containers:
                    print(f"    [Docker] compose up failed: {result.stderr[:500]}")
                    return None
                print(f"    [Docker] compose returned code {result.returncode} but {len(containers)} container(s) running, continuing")

            network_name = f"{self.project_name}_default"

            # 验证网络存在
            try:
                self.docker_client.networks.get(network_name)
            except docker.errors.NotFound:
                networks = self.docker_client.networks.list(
                    names=[f"{self.project_name}"]
                )
                if networks:
                    network_name = networks[0].name
                else:
                    print(f"    [Docker] Network not found, using default name")

            return network_name

        except subprocess.TimeoutExpired:
            print(f"    [Docker] compose up timed out (120s)")
            return None
        except Exception as e:
            print(f"    [Docker] Failed to start environment: {e}")
            return None

    def _create_attacker(self, deps: List[str]):
        """创建 attacker 容器"""
        container_name = f"{self.project_name}-attacker"

        try:
            self.docker_client.images.get(self.ATTACKER_IMAGE)
            image = self.ATTACKER_IMAGE
        except docker.errors.ImageNotFound:
            image = "python:3.11-slim"
            try:
                self.docker_client.images.get(image)
            except docker.errors.ImageNotFound:
                print(f"    [Docker] Pulling {image}...")
                self.docker_client.images.pull(image)

        attacker = self.docker_client.containers.run(
            image,
            command="sleep 3600",
            name=container_name,
            network=self.network_name,
            detach=True,
            remove=False
        )

        # 安装 bash（python:3.11-slim 默认只有 dash）
        attacker.exec_run(["apt-get", "update", "-qq"])
        attacker.exec_run(["apt-get", "install", "-y", "-qq", "bash"])

        # 安装依赖
        if deps:
            # 清洗依赖名
            cleaned = []
            for dep in deps:
                dep_name = dep.split("(")[0].split("#")[0].split(",")[0].strip()
                dep_name = re.sub(r'[^a-zA-Z0-9\-_.]', '', dep_name)
                if dep_name:
                    cleaned.append(dep_name)
            if cleaned:
                exec_result = attacker.exec_run(
                    ["pip", "install", "--quiet", "--disable-pip-version-check"] + cleaned
                )
                if exec_result.exit_code != 0:
                    output = exec_result.output.decode('utf-8', errors='replace')[:200]
                    print(f"    [Docker] pip install warning: {output}")

        return attacker

    def _wait_for_service(self) -> bool:
        """等待目标服务就绪"""
        wait_intervals = [1, 2, 4, 8, 8, 8, 8, 8, 8]
        elapsed = 0

        for interval in wait_intervals:
            if elapsed >= self.service_wait:
                break
            check_cmd = (
                f"python3 -c \""
                f"import socket; s=socket.socket(); s.settimeout(3); "
                f"s.connect(('{self.target_host}', {self.target_port})); "
                f"s.close(); print('OK')\""
            )
            result = self.attacker.exec_run(["sh", "-c", check_cmd])
            if result.exit_code == 0:
                return True
            time.sleep(interval)
            elapsed += interval

        return False

    def exec_in_attacker(self, command: str, timeout: int = 30) -> Tuple[int, str, str]:
        """在 attacker 容器中执行任意命令。

        Args:
            command: Shell 命令
            timeout: 超时时间（秒）

        Returns:
            (exit_code, stdout, stderr)
        """
        if not self.attacker:
            return -1, "", "Attacker container not running"

        try:
            exec_result = self.attacker.exec_run(
                ["bash", "-c", f"timeout {timeout} bash -c {shlex.quote(command)}"],
                demux=True
            )
            exit_code = exec_result.exit_code
            stdout_raw, stderr_raw = (
                exec_result.output if isinstance(exec_result.output, tuple)
                else (exec_result.output, b"")
            )
            stdout = (stdout_raw or b"").decode('utf-8', errors='replace')
            stderr = (stderr_raw or b"").decode('utf-8', errors='replace')
            return exit_code, stdout, stderr
        except Exception as e:
            return -1, "", str(e)

    def exec_script(self, script_content: str, args: str = "",
                    filename: str = "script.py") -> Tuple[int, str, str]:
        """在 attacker 容器中执行 Python 脚本。

        Args:
            script_content: Python 脚本内容
            args: 命令行参数字符串
            filename: 脚本文件名

        Returns:
            (exit_code, stdout, stderr)
        """
        if not self.attacker:
            return -1, "", "Attacker container not running"

        try:
            # 写入脚本到容器
            tar_stream = io.BytesIO()
            with tarfile.open(fileobj=tar_stream, mode='w') as tar:
                script_bytes = script_content.encode('utf-8')
                info = tarfile.TarInfo(name=filename)
                info.size = len(script_bytes)
                tar.addfile(info, io.BytesIO(script_bytes))
            tar_stream.seek(0)
            self.attacker.put_archive('/tmp', tar_stream)

            # 执行脚本
            cmd = f"timeout {self.poc_timeout} python3 /tmp/{filename} {args}"
            exec_result = self.attacker.exec_run(
                ["sh", "-c", cmd],
                demux=True
            )
            exit_code = exec_result.exit_code
            stdout_raw, stderr_raw = (
                exec_result.output if isinstance(exec_result.output, tuple)
                else (exec_result.output, b"")
            )
            stdout = (stdout_raw or b"").decode('utf-8', errors='replace')
            stderr = (stderr_raw or b"").decode('utf-8', errors='replace')
            return exit_code, stdout, stderr
        except Exception as e:
            return -1, "", str(e)

    def install_package(self, package: str) -> Tuple[int, str]:
        """在 attacker 容器中 pip install。

        Returns:
            (exit_code, output)
        """
        if not self.attacker:
            return -1, "Attacker container not running"

        exec_result = self.attacker.exec_run(
            ["pip", "install", "--quiet", "--disable-pip-version-check", package]
        )
        output = exec_result.output.decode('utf-8', errors='replace')
        return exec_result.exit_code, output

    def cleanup(self):
        """清理 attacker 容器和 Docker 环境"""
        if self.attacker:
            try:
                self.attacker.stop(timeout=5)
                self.attacker.remove(force=True)
            except Exception:
                pass
            self.attacker = None

        if self.compose_path and self.project_name:
            try:
                cmd = self.compose_cmd + [
                    "-f", str(self.compose_path),
                    "-p", self.project_name,
                    "down", "-v", "--remove-orphans"
                ]
                subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=30, cwd=str(self.compose_path.parent)
                )
            except Exception:
                pass

        self._started = False


# ============================================================================
# AgentRunner — LLM Agent 交互式 PoC 生成
# ============================================================================

# Agent 可用的工具定义（OpenAI function calling 格式）
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Execute a shell command in the attacker container. "
                "The container is on the same Docker network as the target. "
                "Use this for recon, running tools, testing payloads, etc."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The shell command to execute"
                    }
                },
                "required": ["command"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "http_request",
            "description": (
                "Send an HTTP request to the target service. "
                "This is a convenience wrapper around curl in the attacker container."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "method": {
                        "type": "string",
                        "enum": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"],
                        "description": "HTTP method"
                    },
                    "url": {
                        "type": "string",
                        "description": "Full URL (e.g., http://target:8080/path)"
                    },
                    "headers": {
                        "type": "object",
                        "description": "HTTP headers as key-value pairs",
                        "additionalProperties": {"type": "string"}
                    },
                    "body": {
                        "type": "string",
                        "description": "Request body (for POST/PUT/PATCH)"
                    },
                    "follow_redirects": {
                        "type": "boolean",
                        "description": "Follow HTTP redirects (default: true)"
                    }
                },
                "required": ["method", "url"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_poc",
            "description": (
                "Submit the final PoC script. The script must be a complete, "
                "standalone Python script that accepts --host and --port arguments. "
                "It should exit(0) on success and print '[+] Exploitation successful!' "
                "when the exploit works."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": "Complete Python PoC script content"
                    }
                },
                "required": ["script"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_verification",
            "description": (
                "Submit the verification script. This script independently verifies "
                "that the exploit effect persists. It must accept --host and --port, "
                "exit(0) if verification passes, exit(1) if it fails. "
                "It must NOT depend on poc.py output — it checks effects independently."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "script": {
                        "type": "string",
                        "description": "Complete Python verification script content"
                    }
                },
                "required": ["script"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "submit_requirements",
            "description": (
                "Submit the requirements.txt content listing all pip dependencies "
                "needed by poc.py and verify.py. One package per line."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "requirements": {
                        "type": "string",
                        "description": (
                            "Content of requirements.txt, one package per line "
                            "(e.g., 'requests\\nbeautifulsoup4\\n')"
                        )
                    }
                },
                "required": ["requirements"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "done",
            "description": (
                "Signal that you have finished. Call this after submitting "
                "poc.py, verify.py, and requirements.txt."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
    },
]


def _build_system_prompt(target_host: str, target_port: int) -> str:
    """构建 Agent 的 system prompt"""
    return f"""You are an expert security researcher conducting authorized penetration testing.

You are given a README document describing a known vulnerability in a Docker-based target environment.
The target service is accessible at: {target_host}:{target_port}

Your task:
1. Read and understand the vulnerability described in the README
2. Interact with the target Docker environment to develop a working exploit (PoC)
3. Submit a verified PoC script and a verification script

You have access to these tools:
- bash: Execute bash commands in an attacker container on the same Docker network as the target. The shell is bash.
- http_request: Send HTTP requests to the target (convenience wrapper)
- submit_poc: Submit your final PoC Python script
- submit_verification: Submit your verification Python script
- submit_requirements: Submit the requirements.txt listing all pip dependencies
- done: Signal completion

## Workflow
1. Analyze the README to understand the vulnerability
2. Use bash/http_request to probe the target and understand its current state
3. Develop and test your exploit interactively
4. Once the exploit works, package it into poc.py
5. Create verify.py to independently check the exploit effect
6. Submit all three deliverables:
   a. submit_poc — the PoC script
   b. submit_verification — the verification script
   c. submit_requirements — the pip dependencies (one package per line)
7. Call done to finish

## PoC Script Requirements (poc.py)
- Must be a standalone Python 3 script
- Must use argparse with --host and --port arguments
- Must print "[+] Exploitation successful!" on success
- Must exit(0) on success, exit(1) on failure
- Should include debug output showing what it's doing
- All imports must be at the top of the file

## Verification Script Requirements (verify.py)
CRITICAL constraints:
- verify.py runs INDEPENDENTLY of poc.py — it cannot read poc.py's output
- verify.py must check objective, observable facts that prove the exploit worked:
  * File readable: e.g., /etc/passwd content retrieved
  * Command executed: e.g., `id` returns specific output
  * HTTP response contains specific content proving exploitation
  * Database accessible: SQL query returns results
  * Backdoor/webshell accessible: specific URL returns expected content
- Must accept --host and --port arguments
- exit(0) = verification passed (exploit effect confirmed)
- exit(1) = verification failed
- Must print detailed verification logs

## Important Notes
- The target hostname is '{target_host}' and port is {target_port}
- You are in an attacker container with Python 3 and common tools installed
- The 'requests' library is pre-installed
- If you need additional packages, install them with: pip install <package>
- Be methodical: probe first, then exploit, then verify
- If something doesn't work, analyze the error and try a different approach
"""


class AgentRunner:
    """LLM Agent 交互式 PoC 生成"""

    def __init__(self, llm_client: OpenAI, docker_env: DockerEnvironment,
                 model: str = DEFAULT_MODEL, max_steps: int = MAX_AGENT_STEPS):
        self.client = llm_client
        self.docker_env = docker_env
        self.model = model
        self.max_steps = max_steps
        self.conversation: List[Dict] = []
        self.actions_log: List[AgentAction] = []

        # Agent 提交的脚本
        self._poc_script: Optional[str] = None
        self._verify_script: Optional[str] = None
        self._requirements_txt: Optional[str] = None

    def run(self, readme_content: str, code_blocks: List[CodeBlock],
            images: List[ImageContent], cve_id: str) -> AgentOutput:
        """运行 Agent 直到完成或达到 max_steps。

        Args:
            readme_content: README 文本
            code_blocks: 代码块列表
            images: 图片列表
            cve_id: CVE ID

        Returns:
            AgentOutput with PoC, verify script, etc.
        """
        # 构建 system prompt
        system_prompt = _build_system_prompt(
            self.docker_env.target_host,
            self.docker_env.target_port
        )

        # 构建 user message（README + 代码块 + 图片）
        user_content = self._build_user_message(readme_content, code_blocks, images, cve_id)

        self.conversation = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        return self._run_loop()

    def run_with_feedback(self, feedback: str) -> AgentOutput:
        """带反馈继续运行 Agent。

        在验证失败后调用，向 Agent 提供失败详情并让其重试。
        """
        self.conversation.append({
            "role": "user",
            "content": feedback
        })
        self._poc_script = None
        self._verify_script = None
        self._requirements_txt = None
        return self._run_loop()

    def _run_loop(self) -> AgentOutput:
        """Agent 主循环"""
        for step in range(self.max_steps):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=self.conversation,
                    tools=TOOL_DEFINITIONS,
                    tool_choice="auto",
                )
            except Exception as e:
                print(f"    [Agent] LLM API error at step {step}: {e}")
                break

            message = response.choices[0].message

            if message.tool_calls:
                # 将 assistant message 加入对话
                self.conversation.append({
                    "role": "assistant",
                    "content": message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in message.tool_calls
                    ]
                })

                should_stop = False
                for tool_call in message.tool_calls:
                    tool_name = tool_call.function.name
                    try:
                        tool_args = json.loads(tool_call.function.arguments)
                    except json.JSONDecodeError:
                        tool_args = {}

                    result = self._execute_tool(tool_name, tool_args)

                    # 记录操作
                    self.actions_log.append(AgentAction(
                        step=step,
                        tool_name=tool_name,
                        tool_input=tool_args,
                        tool_output=result[:2000],  # 截断避免过长
                        timestamp=datetime.now().isoformat()
                    ))

                    # 添加 tool result 到对话
                    self.conversation.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": result
                    })

                    if tool_name == "done":
                        should_stop = True

                    print(f"    [Agent] Step {step}: {tool_name} → "
                          f"{result[:100]}{'...' if len(result) > 100 else ''}")

                if should_stop:
                    return self._collect_output(step + 1)
            else:
                # 纯文本回复（无 tool call）
                text = message.content or ""
                self.conversation.append({
                    "role": "assistant",
                    "content": text
                })
                print(f"    [Agent] Step {step}: (text) {text[:100]}{'...' if len(text) > 100 else ''}")

        # max_steps 达到
        print(f"    [Agent] Max steps ({self.max_steps}) reached")
        return self._collect_output(self.max_steps)

    def _execute_tool(self, tool_name: str, tool_args: Dict) -> str:
        """执行单个工具调用"""
        if tool_name == "bash":
            command = tool_args.get("command", "")
            exit_code, stdout, stderr = self.docker_env.exec_in_attacker(command)
            parts = [f"exit_code: {exit_code}"]
            if stdout:
                parts.append(f"stdout:\n{stdout}")
            if stderr:
                parts.append(f"stderr:\n{stderr}")
            return "\n".join(parts)

        elif tool_name == "http_request":
            return self._execute_http_request(tool_args)

        elif tool_name == "submit_poc":
            script = tool_args.get("script", "")
            self._poc_script = script
            return "PoC script received. Remember to also submit a verification script and call done."

        elif tool_name == "submit_verification":
            script = tool_args.get("script", "")
            self._verify_script = script
            return "Verification script received. Remember to also submit requirements.txt and call done."

        elif tool_name == "submit_requirements":
            reqs = tool_args.get("requirements", "")
            self._requirements_txt = reqs
            return "Requirements received. Call done when finished."

        elif tool_name == "done":
            return "Agent finished."

        else:
            return f"Unknown tool: {tool_name}"

    def _execute_http_request(self, args: Dict) -> str:
        """将 http_request 工具转换为 curl 命令并在 attacker 中执行"""
        method = args.get("method", "GET")
        url = args.get("url", "")
        headers = args.get("headers", {})
        body = args.get("body", "")
        follow = args.get("follow_redirects", True)

        curl_parts = ["curl", "-s", "-S"]

        # 显示响应头
        curl_parts.append("-i")

        # Method
        curl_parts.extend(["-X", method])

        # Follow redirects
        if follow:
            curl_parts.append("-L")

        # Headers
        for key, value in headers.items():
            curl_parts.extend(["-H", f"{key}: {value}"])

        # Body
        if body and method in ("POST", "PUT", "PATCH"):
            curl_parts.extend(["-d", body])

        # Timeout
        curl_parts.extend(["--connect-timeout", "10", "--max-time", "30"])

        # URL
        curl_parts.append(url)

        # 构建 shell 命令
        # 需要正确转义，使用 repr 方式构建
        cmd = " ".join(_shell_quote(p) for p in curl_parts)

        exit_code, stdout, stderr = self.docker_env.exec_in_attacker(cmd, timeout=35)
        parts = [f"exit_code: {exit_code}"]
        if stdout:
            # 截断过长响应
            if len(stdout) > 5000:
                parts.append(f"response (truncated to 5000 chars):\n{stdout[:5000]}")
            else:
                parts.append(f"response:\n{stdout}")
        if stderr:
            parts.append(f"curl_error:\n{stderr}")
        return "\n".join(parts)

    def _build_user_message(self, readme_content: str, code_blocks: List[CodeBlock],
                            images: List[ImageContent], cve_id: str):
        """构建发送给 Agent 的初始 user message。

        支持 Vision API 的多模态内容。
        """
        parts = []

        # 文本部分
        text_parts = [f"# Target: {cve_id}\n"]
        text_parts.append("## README\n")
        text_parts.append(readme_content)

        if code_blocks:
            text_parts.append("\n## Extracted Code Blocks\n")
            for i, cb in enumerate(code_blocks):
                text_parts.append(f"### Block {i+1} ({cb.language})")
                if cb.context:
                    text_parts.append(f"Context: {cb.context}")
                text_parts.append(f"```{cb.language}\n{cb.content}\n```\n")

        text_content = "\n".join(text_parts)

        # 如果有图片，使用多模态格式
        if images:
            content_list = [{"type": "text", "text": text_content}]
            for img in images:
                if img.base64_data:
                    content_list.append({
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:{img.mime_type};base64,{img.base64_data}"
                        }
                    })
            return content_list
        else:
            return text_content

    def _collect_output(self, steps_used: int) -> AgentOutput:
        """收集 Agent 输出"""
        # 优先使用 Agent 提交的 requirements，回退到 import 扫描
        if self._requirements_txt:
            reqs = [
                line.strip() for line in self._requirements_txt.splitlines()
                if line.strip() and not line.strip().startswith("#")
            ]
        else:
            reqs = scan_poc_imports(self._poc_script or "")
        return AgentOutput(
            poc_script=self._poc_script or "",
            verify_script=self._verify_script or "",
            requirements=reqs,
            conversation=self.conversation,
            actions_log=self.actions_log,
            finished=self._poc_script is not None,
            steps_used=steps_used
        )


def _shell_quote(s: str) -> str:
    """简单的 shell 参数引用"""
    if not s:
        return "''"
    # 如果不含特殊字符，不需要引用
    if re.match(r'^[a-zA-Z0-9._/:-]+$', s):
        return s
    # 使用单引号包裹，并转义内部单引号
    return "'" + s.replace("'", "'\\''") + "'"


# ============================================================================
# OutputExtractor — 提取输出
# ============================================================================


class OutputExtractor:
    """从 Agent 输出中提取 PoC、验证脚本和依赖"""

    def extract(self, agent_output: AgentOutput) -> Optional[PoCBundle]:
        """提取产物包。

        Returns:
            PoCBundle if poc_script is available, None otherwise
        """
        if not agent_output.poc_script:
            return None

        # 扫描 PoC 和 verify 脚本的依赖
        poc_deps = scan_poc_imports(agent_output.poc_script)
        verify_deps = scan_poc_imports(agent_output.verify_script) if agent_output.verify_script else []
        all_deps = list(set(poc_deps + verify_deps))

        return PoCBundle(
            poc_script=agent_output.poc_script,
            verify_script=agent_output.verify_script,
            requirements=all_deps
        )


# ============================================================================
# VerificationRunner — 独立验证
# ============================================================================


class VerificationRunner:
    """在 Docker 中独立运行 verify.py 验证 PoC 正确性"""

    def run(self, docker_env: DockerEnvironment,
            poc_script: str, verify_script: str) -> VerificationResult:
        """运行 PoC 然后独立验证。

        Args:
            docker_env: Docker 环境
            poc_script: PoC 脚本内容
            verify_script: 验证脚本内容

        Returns:
            VerificationResult
        """
        target_host = docker_env.target_host
        target_port = docker_env.target_port

        # 安装 PoC 依赖
        all_deps = scan_poc_imports(poc_script)
        if verify_script:
            all_deps = list(set(all_deps + scan_poc_imports(verify_script)))
        for dep in all_deps:
            docker_env.install_package(dep)

        # 1. 运行 poc.py
        poc_args = f"--host {target_host} --port {target_port}"
        poc_exit, poc_stdout, poc_stderr = docker_env.exec_script(
            poc_script, args=poc_args, filename="poc.py"
        )
        print(f"    [Verify] poc.py exit_code={poc_exit}")
        if poc_stdout:
            print(f"    [Verify] poc.py stdout: {poc_stdout[:300]}")

        # 2. 运行 verify.py
        if not verify_script:
            return VerificationResult(
                poc_exit_code=poc_exit,
                poc_stdout=poc_stdout,
                poc_stderr=poc_stderr,
                verify_exit_code=-1,
                verify_stdout="",
                verify_stderr="No verification script provided",
                success=False
            )

        verify_args = f"--host {target_host} --port {target_port}"
        verify_exit, verify_stdout, verify_stderr = docker_env.exec_script(
            verify_script, args=verify_args, filename="verify.py"
        )
        print(f"    [Verify] verify.py exit_code={verify_exit}")
        if verify_stdout:
            print(f"    [Verify] verify.py stdout: {verify_stdout[:300]}")

        success = verify_exit == 0
        return VerificationResult(
            poc_exit_code=poc_exit,
            poc_stdout=poc_stdout,
            poc_stderr=poc_stderr,
            verify_exit_code=verify_exit,
            verify_stdout=verify_stdout,
            verify_stderr=verify_stderr,
            success=success
        )


# ============================================================================
# InteractivePoCPipeline — 主 Pipeline
# ============================================================================


class InteractivePoCPipeline:
    """交互式 PoC 生成主 Pipeline（仅生成，不验证）"""

    def __init__(self, result_dir: str, api_key: str = None,
                 api_base: str = None, model: str = DEFAULT_MODEL,
                 max_agent_steps: int = MAX_AGENT_STEPS,
                 poc_timeout: int = 60, service_wait: int = 60):
        self.result_dir = Path(result_dir).expanduser()
        self.result_dir.mkdir(parents=True, exist_ok=True)

        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.api_base = api_base or os.getenv("OPENAI_API_BASE") or OPENAI_BASE_URL
        self.model = model
        self.max_agent_steps = max_agent_steps
        self.poc_timeout = poc_timeout
        self.service_wait = service_wait

        self.content_parser = ContentParser(ImageProcessor())

    def process_cve(self, cve_dir: Path, scanner: VulhubScanner) -> Optional[PoCBundle]:
        """处理单个 CVE：生成 PoC 并保存到文件夹。

        Args:
            cve_dir: CVE 目录路径
            scanner: VulhubScanner 实例

        Returns:
            PoCBundle if successful, None otherwise
        """
        cve_id = scanner.extract_cve_id(cve_dir)
        print(f"\n  Processing: {cve_id}")

        # 1. 解析 README
        readme_path = scanner.find_readme(cve_dir)
        if not readme_path:
            print(f"    No README found, skipping")
            return None

        raw_text, code_blocks, images, links = self.content_parser.parse_readme(
            readme_path, cve_dir
        )

        compose_path = scanner.find_compose(cve_dir)
        if not compose_path:
            print(f"    No docker-compose found, skipping")
            return None

        docker_config = self.content_parser.parse_docker_compose(compose_path)

        # 2. 启动 Docker 环境
        docker_env = DockerEnvironment(
            poc_timeout=self.poc_timeout,
            service_wait=self.service_wait
        )
        started = docker_env.start(cve_dir, docker_config)
        if not started:
            print(f"    Docker environment failed to start, skipping")
            docker_env.cleanup()
            return None

        try:
            # 3. Agent 交互式生成
            llm_client = OpenAI(api_key=self.api_key, base_url=self.api_base)
            agent = AgentRunner(
                llm_client=llm_client,
                docker_env=docker_env,
                model=self.model,
                max_steps=self.max_agent_steps
            )
            agent_output = agent.run(raw_text, code_blocks, images, cve_id)

            # 4. 提取输出
            bundle = OutputExtractor().extract(agent_output)
            if not bundle:
                print(f"    Agent did not produce a PoC script")
                return None

            # 5. 保存到 result/{CVE-ID}/ 文件夹
            self._save_to_folder(cve_id, bundle)
            print(f"    Saved to {self.result_dir / cve_id}")

            return bundle

        except Exception as e:
            print(f"    Error processing {cve_id}: {e}")
            import traceback
            traceback.print_exc()
            return None
        finally:
            # 6. 清理 Docker
            docker_env.cleanup()

    def _save_to_folder(self, cve_id: str, bundle: PoCBundle):
        """保存 PoC 产物到文件夹。

        result/{cve_id}/
        ├── poc.py
        ├── verify.py
        └── requirements.txt
        """
        cve_dir = self.result_dir / cve_id
        cve_dir.mkdir(parents=True, exist_ok=True)

        (cve_dir / "poc.py").write_text(bundle.poc_script, encoding="utf-8")
        (cve_dir / "verify.py").write_text(bundle.verify_script, encoding="utf-8")
        (cve_dir / "requirements.txt").write_text(
            "\n".join(bundle.requirements) + "\n", encoding="utf-8"
        )

    def run(self, vulhub_dir: str, limit: int = None,
            cve_filter: str = None) -> Path:
        """批量处理 CVE，输出到文件夹结构。

        Args:
            vulhub_dir: Vulhub 仓库路径
            limit: 最大处理数量
            cve_filter: CVE ID 过滤（只处理匹配的 CVE）

        Returns:
            结果目录路径
        """
        scanner = VulhubScanner(vulhub_dir)
        cve_dirs = scanner.scan_all()
        print(f"Found {len(cve_dirs)} valid CVE directories")

        # 应用过滤
        if cve_filter:
            cve_dirs = [
                d for d in cve_dirs
                if cve_filter.lower() in scanner.extract_cve_id(d).lower()
            ]
            print(f"Filtered to {len(cve_dirs)} CVEs matching '{cve_filter}'")

        if limit:
            cve_dirs = random.sample(cve_dirs, min(limit, len(cve_dirs)))
            print(f"Randomly sampled {len(cve_dirs)} CVEs")

        succeeded = []
        failed = []

        for i, cve_dir in enumerate(cve_dirs):
            print(f"\n[{i+1}/{len(cve_dirs)}]", end="")

            try:
                bundle = self.process_cve(cve_dir, scanner)
                if bundle:
                    succeeded.append(scanner.extract_cve_id(cve_dir))
            except Exception as e:
                print(f"    Error: {e}")
                failed.append((cve_dir, str(e)))

        print(f"\n{'='*60}")
        print(f"Processed: {len(succeeded)} successful, {len(failed)} failed")
        print(f"Results saved to: {self.result_dir}")

        # 保存失败记录
        if failed:
            error_path = self.result_dir / "errors.json"
            with open(error_path, 'w') as f:
                json.dump(
                    [{"path": str(p), "error": e} for p, e in failed],
                    f, indent=2
                )
            print(f"Error log saved to: {error_path}")

        return self.result_dir


# ============================================================================
# CLI 入口
# ============================================================================


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Interactive PoC Generation Pipeline - LLM Agent explores Docker to generate PoCs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single CVE test
  python interactive_poc_generator.py \\
    --vulhub-dir ~/vulhub \\
    --cve-filter "CVE-2021-41773" \\
    --result-dir /tmp/result

  # Batch processing (first 10)
  python interactive_poc_generator.py \\
    --vulhub-dir ~/vulhub \\
    --result-dir ./result \\
    --limit 10

  # Custom model and API
  python interactive_poc_generator.py \\
    --vulhub-dir ~/vulhub \\
    --model gpt-5.2 \\
    --api-base https://custom-api.example.com/v1 \\
    --api-key sk-xxx
"""
    )
    parser.add_argument("--vulhub-dir", type=str, default="~/vulhub",
                        help="Path to Vulhub repository (default: ~/vulhub)")
    parser.add_argument("--result-dir", type=str, default="./result",
                        help="Result output directory (default: ./result)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit number of CVEs to process")
    parser.add_argument("--cve-filter", type=str, default=None,
                        help="Only process CVEs matching this string")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL,
                        help=f"LLM model for agent (default: {DEFAULT_MODEL})")
    parser.add_argument("--api-key", type=str, default=None,
                        help="API key (default: from OPENAI_API_KEY env)")
    parser.add_argument("--api-base", type=str, default=None,
                        help=f"API base URL (default: OPENAI_API_BASE env or {OPENAI_BASE_URL})")
    parser.add_argument("--max-steps", type=int, default=MAX_AGENT_STEPS,
                        help=f"Max agent interaction steps (default: {MAX_AGENT_STEPS})")
    parser.add_argument("--poc-timeout", type=int, default=60,
                        help="PoC execution timeout in seconds (default: 60)")
    parser.add_argument("--service-wait", type=int, default=60,
                        help="Max wait for service readiness in seconds (default: 60)")

    args = parser.parse_args()

    # 解析 API 配置
    api_key = args.api_key or os.getenv("OPENAI_API_KEY")
    api_base = args.api_base or os.getenv("OPENAI_API_BASE") or OPENAI_BASE_URL

    print("=" * 60)
    print("Interactive PoC Generation Pipeline v2.0")
    print("=" * 60)
    print(f"Vulhub path: {args.vulhub_dir}")
    print(f"Result dir: {args.result_dir}")
    print(f"API base: {api_base}")
    print(f"Model: {args.model}")
    print(f"Max agent steps: {args.max_steps}")
    if args.cve_filter:
        print(f"CVE filter: {args.cve_filter}")
    if args.limit:
        print(f"Limit: {args.limit}")
    print("=" * 60)

    if not api_key:
        print("Error: API key not found. Set OPENAI_API_KEY or use --api-key")
        return 1

    try:
        pipeline = InteractivePoCPipeline(
            result_dir=args.result_dir,
            api_key=api_key,
            api_base=api_base,
            model=args.model,
            max_agent_steps=args.max_steps,
            poc_timeout=args.poc_timeout,
            service_wait=args.service_wait,
        )

        result_path = pipeline.run(
            vulhub_dir=args.vulhub_dir,
            limit=args.limit,
            cve_filter=args.cve_filter,
        )

        print("\n" + "=" * 60)
        print("Pipeline completed!")
        print(f"Results: {result_path}")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
