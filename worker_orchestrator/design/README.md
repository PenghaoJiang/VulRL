# VulRL Worker Orchestration Design - Complete Documentation

## 📚 Document Index

This directory contains the complete technical design for VulRL's distributed worker orchestration system.

### 1. 📝 **Design Reasoning** ([prompt.md](./prompt.md))
- Original design questions and reasoning flow
- Problem statement and module breakdown
- Updated with final technical recommendations

### 2. 🏗️ **Technical Specification** ([WORKER_MANAGEMENT_TECH_SPEC.md](./WORKER_MANAGEMENT_TECH_SPEC.md))
- **Complete implementation guide** with production-ready code
- Worker Router (FastAPI) implementation
- Worker Unit (subprocess) implementation
- Redis state management
- Docker container orchestration
- Error handling and monitoring
- **START HERE for implementation!**

### 3. 📊 **Technology Stack Comparison** ([TECH_STACK_COMPARISON.md](./TECH_STACK_COMPARISON.md))
- Decision matrix for all technology choices
- Comparison of alternatives (Ray vs subprocess, Redis vs PostgreSQL, etc.)
- Performance estimates and resource requirements
- Scaling roadmap (10 → 50 → 500+ workers)
- Development workflow

### 4. 🎨 **Visual Architecture** ([ARCHITECTURE_VISUAL.md](./ARCHITECTURE_VISUAL.md))
- System overview diagrams
- Request flow sequence diagrams
- Worker lifecycle state machine
- Data flow visualization
- Monitoring dashboard mockup
- File structure layout

---

## 🚀 Quick Start

### For Implementers:
1. **Read**: `WORKER_MANAGEMENT_TECH_SPEC.md` (complete code examples)
2. **Reference**: `TECH_STACK_COMPARISON.md` (understand why each choice)
3. **Visualize**: `ARCHITECTURE_VISUAL.md` (see how it all fits together)

### For Reviewers:
1. **Overview**: `ARCHITECTURE_VISUAL.md` (big picture)
2. **Rationale**: `TECH_STACK_COMPARISON.md` (decision justification)
3. **Details**: `WORKER_MANAGEMENT_TECH_SPEC.md` (implementation details)

---

## 🎯 Recommended Architecture Summary

```
SkyRL Trainer (GPU-bound, training)
    ↓ HTTP POST /api/rollout/execute
Worker Router (FastAPI, manages workers)
    ↓ Redis queue
Worker Units (subprocesses, CPU-bound)
    ↓ Docker containers (isolation)
    ↓ HTTP /v1/chat/completions
SkyRL LLM Server (GPU-bound, inference)
```

### Key Technologies:
- **Worker Router**: FastAPI + uvicorn + Redis
- **Worker Units**: Python subprocess + Docker SDK
- **State Management**: Redis (in-memory)
- **LLM Access**: HTTP client (aiohttp)
- **Communication**: HTTP REST + Redis queues

### Why This Stack:
- ✅ **Simple**: Standard Python tools, no complex frameworks
- ✅ **Fast**: Async throughout, Redis for state
- ✅ **Debuggable**: HTTP APIs, structured logs
- ✅ **Scalable**: Can grow from 10 → 500+ workers
- ✅ **Maintainable**: Well-documented, clean separation

---

## 📖 Detailed Component Breakdown

### 1. Worker Router (FastAPI Server)
**File**: `worker_orchestrator/worker_router/main.py`

**Responsibilities**:
- Expose HTTP API for SkyRL trainer
- Manage pool of worker subprocesses
- Route tasks to idle workers via Redis queues
- Monitor worker health and respawn on failure

**Key Endpoints**:
- `POST /api/rollout/execute` - Submit rollout task
- `GET /api/rollout/status/{task_id}` - Get task status/result
- `GET /api/workers/status` - List all workers

**Configuration**:
```yaml
worker_router:
  host: "0.0.0.0"
  port: 5000
  max_workers: 10
  worker_timeout: 1800  # 30 minutes
```

---

### 2. Worker Unit (Subprocess)
**File**: `worker_orchestrator/worker_unit.py`

**Responsibilities**:
- Poll Redis queue for tasks (blocking)
- Setup Docker environments (docker-compose up)
- Execute exploitation loop with LLM queries
- Compute rewards based on observations
- Cleanup Docker and return results

**Key Features**:
- Stateless (all state in Redis)
- Resource-limited (cgroups)
- Graceful shutdown (signal handlers)
- Isolated execution (subprocess + Docker)

**Execution Flow**:
```python
1. Poll Redis queue → BRPOP worker:{id}:queue
2. Setup Docker → docker-compose up
3. Loop (max 20 steps):
   - Query LLM → HTTP /v1/chat/completions
   - Execute action → Docker SDK
   - Compute reward → Custom logic
   - Check done
4. Cleanup → docker-compose down -v
5. Store result → Redis result:{task_id}
```

---

### 3. Redis State Management
**Service**: `redis-server` (localhost:6379)

**Data Structures**:
```
# Worker queues (list)
worker:{worker_id}:queue → [task_id_1, task_id_2, ...]

# Worker metadata (hash)
worker:{worker_id} → {status: "busy", pid: 12345, ...}

# Task metadata (hash)
task:{task_id} → {status: "running", worker_id: "...", ...}

# Results (string, TTL 1 hour)
result:{task_id} → {"reward": 0.85, "trajectory": [...]}
```

**Why Redis**:
- Fast (in-memory)
- Simple (key-value + lists)
- Built-in queue primitives (LPUSH, BRPOP)
- Pub/sub capability (future extension)

---

### 4. Docker Environment Management

**Setup** (per rollout):
```bash
# Worker calls docker-compose
cd /path/to/vulhub/{cve_id}
docker-compose up -d

# Get container info
docker ps --filter "label=com.docker.compose.project={cve_id}"
```

**Execution** (per action):
```python
# Create ephemeral attacker container
container = docker_client.containers.run(
    image="vulrl/attacker:latest",
    command=["bash", "-c", action],
    network_mode="container:{target_container_id}",
    mem_limit="2g",
    cpu_quota=100000,
    detach=True,
    remove=True,
)
```

**Cleanup**:
```bash
docker-compose down -v  # Remove containers + volumes
```

---

### 5. LLM Client (HTTP)

**Code**:
```python
class LLMClient:
    async def query(self, messages, max_tokens=512):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.endpoint}/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": messages,
                    "max_tokens": max_tokens,
                }
            ) as resp:
                result = await resp.json()
                return result["choices"][0]["message"]["content"]
```

**Endpoint**: `http://127.0.0.1:8001` (SkyRL inference engine)

**Why HTTP**:
- Decoupled from SkyRL internals
- Easy to test independently
- Can swap LLM provider easily
- Standard OpenAI-compatible API

---

## 🔄 Complete Request Flow

```
1. SkyRL Generator
   ↓ HTTP POST
   {cve_id, vulhub_path, prompt, llm_endpoint, model_name}

2. Worker Router
   - Find idle worker or spawn new one
   - Assign task → Redis: task:{task_id}
   - Queue task → Redis: LPUSH worker:{id}:queue, task_id
   - Return task_id immediately
   ↓

3. Worker Unit (polls Redis)
   - Receive task_id → BRPOP worker:{id}:queue
   - Setup Docker environment
   - Execute exploitation loop:
     ┌─────────────────────────────┐
     │  Loop (max 20 steps):       │
     │  • Query LLM → action       │ ← HTTP to SkyRL
     │  • Execute → observation    │ ← Docker
     │  • Compute → reward         │
     │  • Check → done?            │
     └─────────────────────────────┘
   - Cleanup Docker
   - Store result → Redis: result:{task_id}
   ↓

4. SkyRL Generator (polls result)
   ↓ HTTP GET /api/rollout/status/{task_id}
   
5. Worker Router
   - Fetch from Redis → result:{task_id}
   - Return {reward, trajectory, metadata}
   ↓

6. SkyRL Generator
   - Collect all rollout results
   - Convert to training input
   - Update policy model
```

---

## 📊 Performance Characteristics

### Latency
| Operation | Latency |
|-----------|---------|
| HTTP request/response | < 5ms |
| Redis queue operation | < 1ms |
| Docker container spawn | 2-5s |
| LLM inference (per token) | 0.5-2s |
| Full rollout | 10-30 minutes |

### Throughput (10 workers)
| Metric | Value |
|--------|-------|
| Concurrent rollouts | 10 |
| Rollouts per hour | 20-60 |
| LLM requests per second | 10-50 (batched) |

### Resource Usage (per worker)
| Resource | Usage |
|----------|-------|
| Memory | ~2.5GB (500MB Python + 2GB Docker) |
| CPU | ~1 core |
| Disk | ~5GB (Docker images) |

**Total for 10 workers**: ~25GB RAM, 10 cores, ~50GB disk

---

## 🛠️ Development Workflow

```bash
# 1. Install dependencies
pip install -r worker_orchestrator/requirements.txt

# 2. Start Redis
redis-server --daemonize yes

# 3. Start Worker Router (development mode)
cd worker_orchestrator
uvicorn worker_router.main:app --reload --port 5000

# 4. Test API
curl -X POST http://localhost:5000/api/rollout/execute \
  -H "Content-Type: application/json" \
  -d '{
    "cve_id": "CVE-2021-12345",
    "vulhub_path": "/data/vulhub/CVE-2021-12345",
    "prompt": "Exploit this vulnerability",
    "llm_endpoint": "http://127.0.0.1:8001",
    "model_name": "Qwen/Qwen2.5-7B-Instruct"
  }'

# Response: {"task_id": "abc-123", "status": "running"}

# 5. Check status
curl http://localhost:5000/api/rollout/status/abc-123

# 6. View API docs
open http://localhost:5000/docs
```

---

## 🔍 Monitoring & Debugging

### Logs
```bash
# Worker Router logs (FastAPI)
tail -f /var/log/worker_router.log

# Worker Unit logs
tail -f /var/log/worker_{worker_id}.log

# Redis logs
redis-cli MONITOR
```

### Metrics (Prometheus)
```
# Endpoint: http://localhost:9090/metrics

vulrl_rollout_requests_total
vulrl_rollout_duration_seconds
vulrl_worker_status{worker_id, status}
vulrl_active_workers
```

### Health Checks
```bash
# Worker Router health
curl http://localhost:5000/api/workers/status

# Redis health
redis-cli PING

# Docker health
docker ps --filter "label=vulrl.worker"
```

---

## 🚧 Known Limitations & Future Work

### Current Limitations
1. **Single-machine only**: All workers on one host
2. **No authentication**: HTTP endpoints are unauthenticated
3. **Limited fault tolerance**: Failed tasks need manual retry
4. **No load balancing**: First-available worker assignment

### Future Enhancements
1. **Multi-machine support**: Deploy workers across multiple hosts
2. **API authentication**: Add JWT or API key authentication
3. **Task retries**: Automatic retry with exponential backoff
4. **Smart routing**: Load balancing based on worker load
5. **Kubernetes deployment**: Containerize for k8s
6. **Distributed Redis**: Redis Cluster for high availability

---

## 📝 Related Documentation

### In Parent Directories:
- `../SKYRL_INFERENCE_INITIALIZATION.md` - How SkyRL initializes LLM inference
- `../QUICK_START_HTTP_ENDPOINT.md` - Enable HTTP endpoint for workers
- `../GENERATOR_COMPARISON.md` - SkyRL generator patterns

### SkyRL Documentation:
- SkyRL official docs: https://docs.skyrl.ai
- SkyRL GitHub: https://github.com/skyworkai/skyrl

---

## 🤝 Contributing

When implementing, follow these principles:
1. ✅ **Async everything**: Use `async`/`await` throughout
2. ✅ **Type hints**: Use Pydantic models for all API data
3. ✅ **Error handling**: Graceful degradation, never crash
4. ✅ **Logging**: Structured logs with context
5. ✅ **Testing**: Unit tests for all components
6. ✅ **Documentation**: Keep this README updated

---

## 📞 Support

For questions about this design:
1. Read the technical specs: `WORKER_MANAGEMENT_TECH_SPEC.md`
2. Check the architecture diagrams: `ARCHITECTURE_VISUAL.md`
3. Review technology choices: `TECH_STACK_COMPARISON.md`

---

**Last Updated**: 2026-03-09
**Status**: Design Complete, Ready for Implementation ✅
