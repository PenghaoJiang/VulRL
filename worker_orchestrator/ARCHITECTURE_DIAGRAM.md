# VulRL Worker Orchestrator - Architecture Diagram

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         VulRL Worker Orchestrator                            │
│                    (Distributed LLM-based Exploit Framework)                 │
└─────────────────────────────────────────────────────────────────────────────┘

Components:
  • Generator (test_simple.py) - Submits tasks and polls for results
  • Worker Router - Task distribution and auto-scaling
  • Redis - Message queue and result storage
  • Worker Units - Execute rollouts with Docker environments
  • LLM Server (vLLM) - Provides AI-guided actions
```

---

## Module Connection Diagram

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT LAYER                                     │
└──────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────┐
    │  Generator / Test Script (test_simple.py)                   │
    │                                                              │
    │  • Builds RolloutRequest(s)                                 │
    │  • Submits via HTTP                                         │
    │  • Polls for completion (every 5s)                          │
    │  • Retrieves results                                        │
    └───────────────────────┬─────────────────────────────────────┘
                            │
                            │ HTTP (POST /api/rollout/execute)
                            │ HTTP (GET /api/rollout/status/{task_id})
                            │
                            ▼

┌──────────────────────────────────────────────────────────────────────────────┐
│                          ORCHESTRATION LAYER                                  │
└──────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────┐
    │  Worker Router (FastAPI Server)                             │
    │  Port: 5000                                                  │
    │                                                              │
    │  Components:                                                 │
    │  ┌────────────────────────────────────────────────────────┐ │
    │  │  Routes (routes/)                                      │ │
    │  │  • /api/rollout/execute  - Submit tasks               │ │
    │  │  • /api/rollout/status   - Check status               │ │
    │  │  • /api/workers/status   - Worker health              │ │
    │  └────────────────────────────────────────────────────────┘ │
    │                                                              │
    │  ┌────────────────────────────────────────────────────────┐ │
    │  │  Worker Pool (worker_pool.py)                         │ │
    │  │  • spawn_worker()      - Auto-scale workers           │ │
    │  │  • get_available_worker() - Find idle worker          │ │
    │  │  • Max workers: 5 (configurable)                      │ │
    │  └────────────────────────────────────────────────────────┘ │
    │                                                              │
    │  ┌────────────────────────────────────────────────────────┐ │
    │  │  Redis Client (redis_client.py)                       │ │
    │  │  • store_result()      - Save rollout results         │ │
    │  │  • get_result()        - Retrieve results             │ │
    │  │  • push_task()         - Queue tasks                  │ │
    │  │  • get_worker_status() - Check worker state           │ │
    │  └────────────────────────────────────────────────────────┘ │
    └────────┬───────────────────────────────────┬────────────────┘
             │                                   │
             │ Subprocess.Popen()                │ Redis Protocol
             │ (spawn worker process)            │ (localhost:6379)
             │                                   │
             ▼                                   ▼

┌──────────────────────────────────────────────────────────────────────────────┐
│                           STORAGE LAYER                                       │
└──────────────────────────────────────────────────────────────────────────────┘

                    ┌────────────────────────────────────────┐
                    │  Redis (In-Memory Data Store)          │
                    │  Port: 6379                            │
                    │                                         │
                    │  Data Structures:                       │
                    │  • task:{task_id}                      │
                    │    → RolloutResult (JSON)              │
                    │                                         │
                    │  • worker:{worker_id}:metadata         │
                    │    → {status, pid, tasks_completed}    │
                    │                                         │
                    │  • worker:{worker_id}:queue            │
                    │    → [task_id1, task_id2, ...]         │
                    │                                         │
                    │  • workers                              │
                    │    → Set of worker IDs                  │
                    └────────────────────────────────────────┘
                                   ▲
                                   │ Redis Protocol
                                   │ BLPOP (blocking pop)
                                   │
                                   │

┌──────────────────────────────────────────────────────────────────────────────┐
│                          EXECUTION LAYER                                      │
└──────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────┐
    │  Worker Unit (worker_unit/main.py)                          │
    │  Process: python worker_unit/main.py --worker-id auto_XXX   │
    │                                                              │
    │  Lifecycle:                                                  │
    │  1. Start                                                    │
    │  2. Register in Redis (status="idle")                       │
    │  3. Poll queue: BLPOP worker:{id}:queue (timeout=5s)       │
    │  4. Execute task                                             │
    │  5. Store result in Redis                                    │
    │  6. Update status back to "idle"                            │
    │  7. Loop back to step 3                                      │
    │                                                              │
    │  Components:                                                 │
    │  ┌────────────────────────────────────────────────────────┐ │
    │  │  Rollout Executor (rollout_executor.py)               │ │
    │  │  • Orchestrates the entire rollout                    │ │
    │  │  • Initializes LLM client and environment             │ │
    │  │  • Runs agent loop                                    │ │
    │  │  • Computes rewards                                   │ │
    │  └────────────────────────────────────────────────────────┘ │
    │                                                              │
    │  ┌────────────────────────────────────────────────────────┐ │
    │  │  Agent Loop (agent_loop.py)                           │ │
    │  │  • Iterative LLM-environment interaction             │ │
    │  │  • For each step:                                     │ │
    │  │    1. Build prompt with observation                   │ │
    │  │    2. Query LLM for action                            │ │
    │  │    3. Execute action in environment                   │ │
    │  │    4. Receive observation                             │ │
    │  │    5. Repeat until max_steps or done                  │ │
    │  └────────────────────────────────────────────────────────┘ │
    └──────┬───────────────────────────────┬──────────────────────┘
           │                               │
           │ HTTP (aiohttp)                │ Subprocess (docker CLI)
           │                               │
           ▼                               ▼

┌──────────────────────────────────────────────────────────────────────────────┐
│                       INFRASTRUCTURE LAYER                                    │
└──────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────┐    ┌────────────────────────────────────┐
│  LLM Server (vLLM)              │    │  Docker Environment                │
│  Port: 8001                     │    │                                     │
│                                 │    │  Components:                        │
│  • Model: qwen2.5-1.5b         │    │  ┌──────────────────────────────┐  │
│  • OpenAI-compatible API        │    │  │ VulhubAdapter                │  │
│  • Endpoint:                    │    │  │ (vulhub_adapter.py)          │  │
│    /v1/chat/completions         │    │  │                              │  │
│                                 │    │  │ • Uses subprocess (docker)   │  │
│  InferenceEngineClientWrapper   │    │  │ • docker compose up/down     │  │
│  • async generate()             │    │  │ • docker exec (bash cmds)    │  │
│  • Mimics SkyRL's interface     │    │  └──────────────────────────────┘  │
│                                 │    │                                     │
└─────────────────────────────────┘    │  ┌──────────────────────────────┐  │
                                       │  │ SecurityEnv                  │  │
                                       │  │ (security_env.py)            │  │
                                       │  │                              │  │
                                       │  │ • Gymnasium-compliant        │  │
                                       │  │ • reset(), step(), close()   │  │
                                       │  └──────────────────────────────┘  │
                                       │                                     │
                                       │  Docker Containers:                 │
                                       │  • Target: vulhub_cve_XXX-cxf-1    │
                                       │  • Attacker: attacker_vulhub_XXX   │
                                       │  • Network: vulhub_XXX_default     │
                                       └────────────────────────────────────┘
```

---

## Data Flow

### 1. Task Submission Flow

```
test_simple.py
    │
    │ RolloutRequest (CVE-2024-28752, prompt, max_steps=3)
    │
    ▼
POST /api/rollout/execute
    │
    ▼
Worker Router
    │
    ├─► Check available workers → Redis (get_worker_status)
    │   ├─ Found idle worker? → Assign task
    │   └─ No idle worker? → Auto-scale
    │       │
    │       ├─► Worker Pool: spawn_worker()
    │       │   └─► subprocess.Popen([python, worker_unit/main.py, --worker-id, auto_XXX])
    │       │
    │       └─► Wait 10s for worker to register as "idle"
    │
    ├─► Generate task_id (UUID)
    │
    ├─► Push task to worker queue → Redis: RPUSH worker:{id}:queue {task_id}
    │
    └─► Store task metadata → Redis: SET task:{task_id} {metadata}
    │
    ▼
Return task_id to client
```

### 2. Worker Execution Flow

```
Worker Unit (auto_XXX)
    │
    │ 1. Register in Redis
    ├─► SET worker:auto_XXX:metadata {status: "idle", pid: XXX, ...}
    │
    │ 2. Poll for task (blocking)
    ├─► BLPOP worker:auto_XXX:queue 5  # Wait up to 5 seconds
    │   │
    │   ├─ Got task_id? → Process it
    │   └─ Timeout? → Loop back
    │
    │ 3. Update status to "busy"
    ├─► HSET worker:auto_XXX:metadata status "busy"
    ├─► HSET worker:auto_XXX:metadata current_task "{task_id}"
    │
    │ 4. Execute Rollout
    ├─► RolloutExecutor.execute(request)
    │   │
    │   ├─► Initialize LLM Client (http://localhost:8001)
    │   │
    │   ├─► Initialize Environment
    │   │   ├─► VulhubAdapter.setup()
    │   │   │   ├─ docker compose -p vulhub_XXX up -d
    │   │   │   ├─ Discover target container
    │   │   │   ├─ Start attacker container
    │   │   │   └─ Get service URL (http://localhost:XXXXX)
    │   │   │
    │   │   └─► SecurityEnv.reset()
    │   │
    │   ├─► Run Agent Loop (max_steps=3)
    │   │   │
    │   │   │ For step in range(max_steps):
    │   │   │
    │   │   ├─► Build prompt (system + observation)
    │   │   │
    │   │   ├─► LLM: POST /v1/chat/completions
    │   │   │   └─ Response: action (bash command)
    │   │   │
    │   │   ├─► Environment: step(action)
    │   │   │   ├─ docker exec attacker_XXX bash -c "{command}"
    │   │   │   └─ Return: observation, reward, done
    │   │   │
    │   │   └─► Store trajectory step
    │   │
    │   ├─► Cleanup Environment
    │   │   ├─ docker stop attacker_XXX
    │   │   └─ docker compose -p vulhub_XXX down -v
    │   │
    │   └─► Compute rewards
    │
    │ 5. Store result
    ├─► SET task:{task_id} {RolloutResult JSON}
    ├─► EXPIRE task:{task_id} 3600  # TTL 1 hour
    │
    │ 6. Update worker status back to "idle"
    ├─► HSET worker:auto_XXX:metadata status "idle"
    ├─► HSET worker:auto_XXX:metadata current_task "null"
    ├─► HINCRBY worker:auto_XXX:metadata tasks_completed 1
    │
    └─► Loop back to step 2 (poll for next task)
```

### 3. Result Retrieval Flow

```
test_simple.py (polling loop)
    │
    │ Every 5 seconds:
    │
    ├─► GET /api/rollout/status/{task_id}
    │   │
    │   ▼
    │   Worker Router
    │   │
    │   ├─► Redis: GET task:{task_id}
    │   │
    │   ├─ Found? → Return RolloutResult
    │   └─ Not found? → Return status="running"
    │
    ├─ Status == "completed"? → Return result
    ├─ Status == "failed"? → Raise error
    └─ Status == "running"? → Sleep 5s, retry
```

---

## Parallel Execution Example

```
Timeline of Parallel Execution (2 workers, 2 tasks):

t=0s    test_simple.py submits 2 tasks simultaneously
        │
        ├─► Task 1 (6c479002) → Worker Router
        └─► Task 2 (f4e086d2) → Worker Router

t=0s    Worker Router auto-scales
        │
        ├─► spawn_worker() → auto_b0952b21
        └─► spawn_worker() → auto_43a3544a

t=2s    Workers register as "idle"
        │
        ├─► Redis: worker:auto_b0952b21:metadata {status: "idle"}
        └─► Redis: worker:auto_43a3544a:metadata {status: "idle"}

t=2s    Worker Router assigns tasks
        │
        ├─► RPUSH worker:auto_b0952b21:queue "6c479002"
        └─► RPUSH worker:auto_43a3544a:queue "f4e086d2"

t=2s    Workers pick up tasks (BLPOP)
        │
        ├─► Worker auto_b0952b21: Processing task 6c479002
        │   ├─ Update status to "busy"
        │   ├─ Setup Docker environment
        │   └─ Execute agent loop
        │
        └─► Worker auto_43a3544a: Processing task f4e086d2
            ├─ Update status to "busy"
            ├─ Setup Docker environment
            └─ Execute agent loop

t=2-47s Both workers executing in PARALLEL
        │
        ├─► Worker auto_b0952b21:
        │   ├─ Step 1: LLM → action → docker exec → observation
        │   ├─ Step 2: LLM → action → docker exec → observation
        │   └─ Step 3: LLM → action → docker exec → observation
        │
        └─► Worker auto_43a3544a:
            ├─ Step 1: LLM → action → docker exec → observation
            ├─ Step 2: LLM → action → docker exec → observation
            └─ Step 3: LLM → action → docker exec → observation

t=47s   Worker auto_b0952b21 completes
        │
        ├─► Store result in Redis: task:6c479002
        ├─► Update status to "idle"
        └─► Loop back to polling

t=48s   Worker auto_43a3544a completes
        │
        ├─► Store result in Redis: task:f4e086d2
        ├─► Update status to "idle"
        └─► Loop back to polling

t=0-50s test_simple.py polling both tasks
        │
        ├─► Poll task 6c479002 every 5s
        │   └─ t=47s: status="completed" → retrieved
        │
        └─► Poll task f4e086d2 every 5s
            └─ t=48s: status="completed" → retrieved

t=50s   Test complete
        │
        └─► Verify: Different worker IDs → ✓ Parallel execution confirmed!
```

---

## Key Design Patterns

### 1. **Auto-Scaling Pattern**
- Worker Router spawns workers on-demand
- Max workers configurable (default: 5)
- Workers register themselves when ready
- No "starting" status – wait for true "idle"

### 2. **Active Polling Pattern**
- Generator polls Worker Router every 5s
- Worker Router queries Redis for results
- Timeout: 120s per task
- Retry on transient errors

### 3. **Message Queue Pattern**
- Redis used as task queue
- BLPOP for blocking pop (worker waits for task)
- RPUSH to enqueue tasks
- Each worker has dedicated queue: `worker:{id}:queue`

### 4. **Subprocess-based Docker Interaction**
- Avoids Python Docker SDK (proxy issues)
- Uses `docker` CLI directly via `subprocess.run()`
- Commands: `docker compose up/down`, `docker exec`

### 5. **Self-contained Worker Units**
- All VulRL code copied into `worker_unit/`
- No imports from SkyRL project
- Portable and independent

---

## Technology Stack

| Component          | Technology                    | Purpose                          |
|--------------------|-------------------------------|----------------------------------|
| Worker Router      | FastAPI (Python)              | HTTP API for task orchestration  |
| Redis              | Redis 5.0+                    | Message queue + result storage   |
| Worker Unit        | Python (asyncio)              | Task execution                   |
| LLM Server         | vLLM (OpenAI-compatible)      | LLM inference                    |
| Docker             | Docker + Docker Compose       | Vulnerable environment setup     |
| Environment        | VulhubAdapter (subprocess)    | Docker CLI wrapper               |
| HTTP Client        | aiohttp                       | Async HTTP requests              |
| Process Management | subprocess.Popen              | Worker spawning                  |

---

## Port Assignments

| Service        | Port | Protocol | Purpose                    |
|----------------|------|----------|----------------------------|
| Worker Router  | 5000 | HTTP     | Task submission & status   |
| LLM Server     | 8001 | HTTP     | LLM inference API          |
| Redis          | 6379 | TCP      | Message queue & storage    |
| Vulhub Target  | Auto | HTTP     | Vulnerable service (random)|

---

## File Structure

```
worker_orchestrator/
├── worker_router/              # Task orchestration
│   ├── server.py              # FastAPI server
│   ├── routes/
│   │   ├── rollout.py         # POST /api/rollout/execute
│   │   └── workers.py         # GET /api/workers/status
│   ├── worker_pool.py         # Auto-scaling logic
│   ├── redis_client.py        # Redis wrapper
│   └── models.py              # Pydantic models
│
├── worker_unit/               # Task execution
│   ├── main.py                # Worker entry point
│   ├── rollout_executor.py   # Rollout orchestration
│   ├── agent_loop.py          # LLM-environment loop
│   ├── docker/
│   │   ├── vulhub_adapter.py  # Docker CLI wrapper
│   │   └── env_types.py       # Standard types
│   ├── env/
│   │   └── security_env.py    # Gymnasium-compliant env
│   └── reward/
│       └── reward_calculator.py # Reward computation
│
├── ez_llm_server/             # LLM client
│   └── client/
│       └── inference_client_wrapper.py  # SkyRL-compatible client
│
├── ez_generator/              # Generator (SkyRL-compatible)
│   ├── ez_vulrl_generator.py  # Main generator
│   └── worker_router_client.py # HTTP client
│
└── test/
    └── ez_generator/
        ├── test_simple.py     # Parallel test
        └── test_simple.sh     # Test runner
```

---

## Scalability

| Aspect              | Current         | Scalable To                     |
|---------------------|-----------------|---------------------------------|
| Worker Units        | 5 (configurable)| Hundreds (distributed Redis)    |
| Tasks/sec           | ~0.5            | 10+ (with more workers)         |
| LLM Server          | 1 (local)       | Multiple (load balancer)        |
| Redis               | 1 (local)       | Cluster (Redis Sentinel/Cluster)|
| Docker Environments | 1 per worker    | 1 per worker (isolated)         |

---

## Next Steps

1. **Prompt Engineering**: Fix LLM to output bash commands only
2. **Reward Function**: Implement actual exploit success detection
3. **Monitoring**: Add Prometheus metrics
4. **Distributed**: Support remote workers (networked Redis)
5. **Fault Tolerance**: Handle worker crashes gracefully
