# VulRL Worker Orchestration - Visual Architecture

## System Overview

```
┌────────────────────────────────────────────────────────────────────┐
│                         HOST MACHINE                               │
│                                                                    │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │                    SkyRL Training Process                     │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │  VulRLGenerator (Custom Generator)                      │  │ │
│  │  │  - Implements GeneratorInterface                        │  │ │
│  │  │  - Calls Worker Router HTTP API for rollouts            │  │ │
│  │  └────────────┬────────────────────────────────────────────┘  │ │
│  │               │                                               │ │
│  │               │ Uses inference_engine_client                  │ │
│  │               ▼                                               │ │
│  │  ┌─────────────────────────────────────────────────────────┐  │ │
│  │  │  InferenceEngineClient                                  │  │ │
│  │  │  HTTP Endpoint: http://127.0.0.1:8001                   │  │ │
│  │  │  - /v1/chat/completions                                 │  │ │
│  │  │  - /v1/completions                                      │  │ │
│  │  └─────────────┬───────────────────────────────────────────┘  │ │
│  │                │                                              │ │
│  │                │ Routes to vLLM engines                       │ │
│  │                ▼                                              │ │
│  │  ┌────────┬────────┬────────┬────────┐                        │ │
│  │  │ vLLM   │ vLLM   │ vLLM   │ vLLM   │                        │ │
│  │  │Engine 1│Engine 2│Engine 3│Engine 4│                        │ │
│  │  │ GPU 0  │ GPU 1  │ GPU 2  │ GPU 3  │                        │ │
│  │  └────────┴────────┴────────┴────────┘                        │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                           ▲                                        │
│                           │ HTTP: /v1/chat/completions             │
│                           │                                        │
│  ┌────────────────────────┼────────────────────────────────────┐   │
│  │  Worker Router (FastAPI)                                    │   │
│  │  http://localhost:5000 │                                    │   │
│  │  ┌─────────────────────┼──────────────────────────────────┐ │   │
│  │  │  API Endpoints      │                                  │ │   │
│  │  │  POST /api/rollout/execute ← From SkyRL Generator      │ │   │
│  │  │  GET  /api/rollout/status/{task_id}                    │ │   │
│  │  │  GET  /api/workers/status                              │ │   │
│  │  └────────────────────────────────────────────────────────┘ │   │
│  │                                                             │   │
│  │  ┌────────────────────────────────────────────────────────┐ │   │
│  │  │  WorkerPool (manages 10 worker subprocesses)           │ │   │
│  │  │  - Spawn workers on demand                             │ │   │
│  │  │  - Monitor health                                      │ │   │
│  │  │  - Route tasks to idle workers                         │ │   │
│  │  └──────────────┬─────────────────────────────────────────┘ │   │
│  └─────────────────┼───────────────────────────────────────────┘   │
│                    │                                               │
│                    │ Pushes tasks to Redis queues                  │
│                    ▼                                               │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │              Redis (State Management)                       │   │
│  │  localhost:6379                                             │   │
│  │  ┌──────────────────────────────────────────────────────┐   │   │
│  │  │ Task Queues:                                         │   │   │
│  │  │  - worker:uuid-1:queue → [task_id_1, task_id_2]      │   │   │
│  │  │  - worker:uuid-2:queue → [task_id_3]                 │   │   │
│  │  │  - ...                                               │   │   │
│  │  ├──────────────────────────────────────────────────────┤   │   │
│  │  │ Worker State:                                        │   │   │
│  │  │  - worker:uuid-1:status → "busy"                     │   │   │
│  │  │  - worker:uuid-2:status → "idle"                     │   │   │
│  │  ├──────────────────────────────────────────────────────┤   │   │
│  │  │ Task Metadata:                                       │   │   │
│  │  │  - task:task_id:status → "running"                   │   │   │
│  │  │  - task:task_id:request → {...}                      │   │   │
│  │  ├──────────────────────────────────────────────────────┤   │   │
│  │  │ Results (TTL 1 hour):                                │   │   │
│  │  │  - result:task_id → {reward, trajectory, ...}        │   │   │
│  │  └──────────────────────────────────────────────────────┘   │   │
│  └────────────────────┬────────────────────────────────────────┘   │
│                       │                                            │
│                       │ Workers poll queues (BRPOP)                │
│                       │                                            │
│  ┌────────────────────┴────────────────────────────────────────┐   │
│  │         Worker Units (Python Subprocesses)                  │   │
│  │  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐    │   │
│  │  │  Worker #1    │  │  Worker #2    │  │  Worker #3    │    │   │
│  │  │  PID: 12345   │  │  PID: 12346   │  │  PID: 12347   │    │   │
│  │  │  Status: busy │  │  Status: idle │  │  Status: busy │    │   │
│  │  └───────┬───────┘  └───────────────┘  └───────┬───────┘    │   │
│  │          │                                      │           │   │
│  │          │ Manages Docker                       │           │   │
│  │          ▼                                      ▼           │   │
│  │  ┌──────────────────────┐            ┌───────────────────┐  │   │
│  │  │  Docker Environment  │            │ Docker Environment│  │   │
│  │  │  ┌────────────────┐  │            │ ┌────────────────┐│  │   │
│  │  │  │  Attacker      │  │            │ │  Attacker      ││  │   │
│  │  │  │  Container     │  │            │ │  Container     ││  │   │
│  │  │  └────────────────┘  │            │ └────────────────┘│  │   │
│  │  │  ┌────────────────┐  │            │ ┌────────────────┐│  │   │
│  │  │  │  Target        │  │            │ │  Target        ││  │   │
│  │  │  │  (Vulnerable)  │  │            │ │  (Vulnerable)  ││  │   │
│  │  │  └────────────────┘  │            │ └────────────────┘│  │   │
│  │  └──────────────────────┘            └───────────────────┘  │   │
│  └─────────────────────────────────────────────────────────────┘   │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

## Request Flow Diagram

```
┌──────────────┐
│ SkyRL Trainer│
│ (Generator)  │
└──────┬───────┘
       │
       │ 1. POST /api/rollout/execute
       │    {cve_id, vulhub_path, prompt, llm_endpoint, model_name}
       │
       ▼
┌──────────────────────────────────────────────────┐
│           Worker Router (FastAPI)                │
│                                                  │
│  2. Get available worker from pool               │
│     - Check Redis for idle workers               │
│     - Or spawn new worker subprocess             │
│                                                  │
│  3. Create task_id and assign to worker          │
│     - Redis: task:task_id → {status: "running"}│
│     - Redis: worker:worker_id → {status: "busy"}│
│                                                  │
│  4. Push task to worker queue                    │
│     - Redis: LPUSH worker:worker_id:queue task_id│
│                                                  │
│  5. Return immediately                           │
│     → {task_id, status: "running", worker_id}   │
└──────────────────────────────────────────────────┘
       │
       │ 6. Worker polls queue (background)
       │    Redis: BRPOP worker:worker_id:queue
       │
       ▼
┌──────────────────────────────────────────────────┐
│         Worker Unit (Subprocess)                 │
│                                                  │
│  7. Receive task from queue                      │
│     - Get task details from Redis                │
│                                                  │
│  8. Setup Docker environment                     │
│     - docker-compose up                          │
│     - Get container IPs                          │
│                                                  │
│  9. Execute exploitation loop (20 steps max)     │
│     ┌──────────────────────────────────────┐    │
│     │  For each step:                      │    │
│     │  a. Query LLM for action ────────────┼────┼──┐
│     │  b. Execute action in Docker         │    │  │
│     │  c. Observe result                   │    │  │
│     │  d. Compute reward                   │    │  │
│     │  e. Check if done                    │    │  │
│     └──────────────────────────────────────┘    │  │
│                                                  │  │
│  10. Cleanup Docker                              │  │
│      - docker-compose down -v                   │  │
│                                                  │  │
│  11. Store result in Redis                       │  │
│      - result:task_id → {reward, trajectory}   │  │
│      - task:task_id:status → "completed"       │  │
│                                                  │  │
│  12. Mark worker as idle                         │  │
│      - worker:worker_id:status → "idle"        │  │
└──────────────────────────────────────────────────┘  │
       ▲                                                │
       │                                                │
       │ a. HTTP POST /v1/chat/completions             │
       │    {messages, max_tokens, temperature}        │
       │                                                │
       └────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────┐
│    SkyRL InferenceEngineClient                  │
│    http://127.0.0.1:8001                        │
│                                                  │
│    Routes request to vLLM engine                │
│    Returns: {choices: [{message: {content}}]}   │
└──────────────────────────────────────────────────┘
```

---

## Worker Lifecycle

```
┌─────────────┐
│   Spawn     │  Worker Router spawns subprocess
│   Worker    │  python -m worker_orchestrator.worker_unit --worker-id uuid
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Initialize  │  - Connect to Redis
│             │  - Setup signal handlers
│             │  - Initialize Docker client
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    Idle     │◄─────────────────────────────┐
│             │  Waiting for tasks           │
│   Status:   │  BRPOP worker:id:queue (5s)  │
│   "idle"    │                              │
└──────┬──────┘                              │
       │                                     │
       │ Task received                       │
       ▼                                     │
┌─────────────┐                              │
│    Busy     │  Executing rollout           │
│             │  - Setup Docker              │
│   Status:   │  - Query LLM (loop)          │
│   "busy"    │  - Execute actions           │
│             │  - Compute rewards           │
│             │  - Cleanup Docker            │
└──────┬──────┘                              │
       │                                     │
       │ Task completed                      │
       └─────────────────────────────────────┘
       │
       │ Error or shutdown signal
       ▼
┌─────────────┐
│  Cleanup    │  - Close Redis connection
│             │  - Kill any Docker containers
│             │  - Remove from worker pool
└──────┬──────┘
       │
       ▼
┌─────────────┐
│    Dead     │  Process exits
│             │  Status: "dead" in Redis
└─────────────┘
```

---

## Data Flow

```
┌──────────────────────────────────────────────────────────────────┐
│                     SkyRL Training Loop                          │
│                                                                  │
│  1. Get batch of prompts from dataset                           │
│  2. For each prompt, call VulRLGenerator.generate()             │
│     ├─ VulRLGenerator calls Worker Router HTTP API              │
│     └─ Waits for rollout results                                │
│  3. Collect rewards and trajectories                            │
│  4. Convert to training input                                   │
│  5. Update policy model                                         │
└────────────┬─────────────────────────────────────────────────────┘
             │
             │ HTTP POST: {cve_id, prompt, ...}
             ▼
┌──────────────────────────────────────────────────────────────────┐
│                      Worker Router                               │
│                                                                  │
│  Request Flow:                                                   │
│  ┌────────┐  ┌──────────┐  ┌───────────┐  ┌────────────┐       │
│  │ Receive│─→│ Validate │─→│ Find      │─→│ Queue Task │       │
│  │ Request│  │ Request  │  │ Worker    │  │ in Redis   │       │
│  └────────┘  └──────────┘  └───────────┘  └────────────┘       │
│                                                                  │
│  Response Flow:                                                  │
│  ┌──────────┐  ┌───────────┐                                    │
│  │ Return   │←─│ Create    │                                    │
│  │ task_id  │  │ task_id   │                                    │
│  └──────────┘  └───────────┘                                    │
└────────────┬─────────────────────────────────────────────────────┘
             │
             │ Redis: LPUSH worker:id:queue, task_id
             ▼
┌──────────────────────────────────────────────────────────────────┐
│                          Redis                                   │
│                                                                  │
│  Queue: [task_1, task_2, task_3, ...]                           │
│  State: {worker_id: status, task_id: metadata, ...}             │
└────────────┬─────────────────────────────────────────────────────┘
             │
             │ BRPOP (blocking pop)
             ▼
┌──────────────────────────────────────────────────────────────────┐
│                       Worker Unit                                │
│                                                                  │
│  Execution Flow:                                                 │
│  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐    │
│  │ Setup  │─→│ LLM    │─→│ Docker │─→│ Reward │─→│ Store  │    │
│  │ Docker │  │ Query  │  │ Exec   │  │ Compute│  │ Result │    │
│  └────────┘  └────┬───┘  └────────┘  └────────┘  └────┬───┘    │
│                   │                                    │        │
│                   │ HTTP /v1/chat/completions          │        │
│                   ▼                                    ▼        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ SkyRL LLM Server                Redis: result:task_id   │   │
│  └──────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

---

## Technology Stack Visual

```
┌─────────────────────────────────────────────────────────────┐
│                    Application Layer                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │   SkyRL      │  │   Worker     │  │   Worker     │     │
│  │   Generator  │  │   Router     │  │   Unit       │     │
│  │              │  │              │  │              │     │
│  │  (Custom)    │  │  FastAPI     │  │  asyncio     │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                  Communication Layer                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │     HTTP     │  │    Redis     │  │   Docker     │     │
│  │   REST API   │  │    Queue     │  │     SDK      │     │
│  │              │  │              │  │              │     │
│  │  aiohttp     │  │  redis-py    │  │  docker-py   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                    Storage Layer                            │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │    Redis     │  │   Docker     │  │   vLLM       │     │
│  │  (In-memory) │  │  Containers  │  │   Cache      │     │
│  │              │  │              │  │              │     │
│  │  State Store │  │  Env Isolation│ │  KV Cache    │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│                  Infrastructure Layer                       │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │              Linux Host (Ubuntu 22.04)               │  │
│  │  • Python 3.10+                                      │  │
│  │  • Docker 24.0+                                      │  │
│  │  • CUDA 12.1+ (for GPUs)                            │  │
│  │  • 64GB RAM, 10 CPU cores, 4 GPUs                   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Monitoring Dashboard (Conceptual)

```
┌────────────────────────────────────────────────────────────────┐
│                 VulRL Worker Orchestrator                      │
│                      Status Dashboard                          │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  System Overview                                               │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Active Workers: 8/10                                    │ │
│  │  Queued Tasks:   3                                       │ │
│  │  Running Tasks:  8                                       │ │
│  │  Completed:      157                                     │ │
│  │  Failed:         2                                       │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
│  Worker Status                                                 │
│  ┌────┬─────────┬────────┬──────────┬─────────────────────┐  │
│  │ ID │  Status │  CPU%  │  Memory  │  Current Task       │  │
│  ├────┼─────────┼────────┼──────────┼─────────────────────┤  │
│  │  1 │  busy   │  87%   │  2.1GB   │  task-abc123        │  │
│  │  2 │  busy   │  93%   │  2.3GB   │  task-def456        │  │
│  │  3 │  idle   │   2%   │  0.5GB   │  -                  │  │
│  │  4 │  busy   │  78%   │  1.9GB   │  task-ghi789        │  │
│  │ .. │   ...   │  ...   │  ...     │  ...                │  │
│  └────┴─────────┴────────┴──────────┴─────────────────────┘  │
│                                                                │
│  Recent Rollouts                                               │
│  ┌──────────┬─────────────┬────────┬────────┬──────────┐     │
│  │ Task ID  │  CVE ID     │ Status │ Reward │ Duration │     │
│  ├──────────┼─────────────┼────────┼────────┼──────────┤     │
│  │ abc123   │ CVE-2021-.. │  ✓     │  0.85  │  18m     │     │
│  │ def456   │ CVE-2022-.. │  ⏳    │  -     │  12m     │     │
│  │ ghi789   │ CVE-2020-.. │  ✗     │  0.0   │  30m     │     │
│  └──────────┴─────────────┴────────┴────────┴──────────┘     │
│                                                                │
│  Performance Metrics                                           │
│  ┌──────────────────────────────────────────────────────────┐ │
│  │  Avg Rollout Duration:  15.3 minutes                     │ │
│  │  Success Rate:          78%                              │ │
│  │  Avg Reward:            0.67                             │ │
│  │  LLM Queries/sec:       12.5                             │ │
│  │  Docker Containers:     16 running                       │ │
│  └──────────────────────────────────────────────────────────┘ │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
VulRL/
├── SkyRL/                          # SkyRL submodule
│   └── skyrl-train/
│       └── ...
├── examples/
│   └── vulrl/
│       ├── main_vulrl.py           # Entry point
│       ├── vulrl_generator.py      # Custom generator
│       ├── vulrl_env.py            # Environment (minimal)
│       └── run_vulrl.sh            # Training script
├── worker_orchestrator/
│   ├── worker_router/
│   │   ├── __init__.py
│   │   ├── main.py                 # FastAPI app
│   │   ├── worker_pool.py          # Worker management
│   │   ├── models.py               # Pydantic models
│   │   └── config.py               # Configuration
│   ├── worker_unit.py              # Worker subprocess
│   ├── docker/
│   │   ├── attacker/
│   │   │   └── Dockerfile          # Attacker image
│   │   └── docker-compose.yml
│   ├── config.yaml
│   ├── requirements.txt
│   ├── start.sh
│   └── design/                     # Documentation
│       ├── WORKER_MANAGEMENT_TECH_SPEC.md
│       ├── TECH_STACK_COMPARISON.md
│       ├── ARCHITECTURE_VISUAL.md
│       └── design_n_prompt_v2/
│           ├── prompt.md
│           └── ...
├── dataset/
│   └── ...
└── README.md
```

This visual architecture provides a complete picture of how all components interact! 🎯
