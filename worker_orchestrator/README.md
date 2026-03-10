# VulRL Worker Orchestrator

Distributed worker orchestration system for VulRL penetration testing training with SkyRL.

## 🏗️ Architecture

```
SkyRL Trainer (GPU-bound)
    ↓ HTTP REST API
Worker Router (FastAPI)
    ↓ Redis Queue
Worker Units (Subprocesses)
    ↓ Docker Containers
    ↓ Python Client (InferenceEngineClientWrapper)
vLLM Server (GPU-bound, local Qwen 2.5 1.5B)
```

## 📁 Project Structure

```
worker_orchestrator/
├── worker_router/              # FastAPI server
│   ├── app.py                  # Main FastAPI app
│   ├── models.py               # Pydantic models
│   ├── config.py               # Config loader
│   ├── redis_client.py         # Redis wrapper
│   ├── worker_pool.py          # Worker subprocess management
│   ├── routes/
│   │   ├── rollout.py          # Rollout endpoints
│   │   └── workers.py          # Worker management endpoints
│   └── utils/
│       ├── logger.py           # File logging
│       └── exceptions.py       # Custom exceptions
│
├── worker_unit/                # Worker subprocess
│   ├── main.py                 # Worker entry point
│   ├── docker_manager.py       # Docker operations (demo)
│   └── reward_calculator.py    # Reward computation
│
├── ez_llm_server/              # LLM server (vLLM wrapper)
│   ├── client/                 # Python client
│   │   └── inference_client_wrapper.py  # SkyRL-compatible client
│   ├── test/                   # Test scripts
│   └── README.md               # LLM server docs
│
├── logs/                       # Log files
├── venv/                       # Shared virtual environment
│
├── config.yaml                 # Configuration
├── .env                        # Environment variables
├── requirements.txt            # All dependencies (including vLLM)
│
├── setup.sh                    # Setup venv and install deps
├── start_all.sh                # Start all services ⭐
├── stop_all.sh                 # Stop all services
├── start_worker_router.sh      # Start Worker Router only
├── stop_worker_router.sh       # Stop Worker Router only
├── start_llm_server.sh         # Start vLLM server only
├── stop_llm_server.sh          # Stop vLLM server only
│
├── STARTUP_GUIDE.md            # Complete startup guide
└── README.md                   # This file
```

## 🚀 Quick Start

### 1. Setup Virtual Environment & Install Dependencies

```bash
cd /mnt/e/git_fork_folder/VulRL/worker_orchestrator  # WSL

# Run setup script (creates venv and installs all dependencies)
bash setup.sh
```

This installs:
- FastAPI, Redis, aiohttp (Worker Router)
- vLLM (LLM Server)
- Docker SDK (Workers)

### 2. Ensure Model is Available

The model should be at:
```
/mnt/e/models/qwen2.5-1.5b  (WSL)
E:\models\qwen2.5-1.5b       (Windows)
```

### 3. Start All Services

```bash
bash start_all.sh
```

This starts:
- ✅ Redis (if not running)
- ✅ vLLM server (background)
- ✅ Worker Router (foreground)

Press `Ctrl+C` to stop all services.

### 4. Verify Services

```bash
# Check Redis
redis-cli ping

# Check LLM server
curl http://127.0.0.1:8001/health

# Check Worker Router
curl http://localhost:5000/health
```

### 5. Test API

```bash
# View API docs
open http://localhost:5000/docs

# Submit a rollout
cd test/worker_router
bash _api_rollout_execute.sh

# Check workers
bash _api_workers_status.sh
```

## 📖 API Endpoints

### Rollout Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/rollout/execute` | POST | Submit rollout task |
| `/api/rollout/status/{task_id}` | GET | Get task status/result |

### Worker Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/workers/status` | GET | Get all workers status |
| `/api/workers/{worker_id}/shutdown` | POST | Shutdown specific worker |

### Health & Info

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Service info |
| `/health` | GET | Health check |

## 📝 Logging

All logs are written to `logs/` directory:
- `worker_router.log` - Worker Router logs
- `llm_server.log` - vLLM server logs (if started with start_all.sh)

Format:
```
time <timestamp>; request entry point: <function>; request: <input>
time <timestamp>; request entry point: <function>; request: <input>; return: <output>
```

## 🔧 Configuration

### Worker Router Settings

```yaml
worker_router:
  host: "0.0.0.0"          # Server host
  port: 5000               # Server port
  max_workers: 10          # Maximum worker subprocesses
  worker_timeout: 1800     # Worker timeout (seconds)
```

### Redis Settings

```yaml
redis:
  host: "localhost"
  port: 6379
  db: 0
  # password from .env
```

### LLM Settings

```yaml
llm:
  default_endpoint: "http://127.0.0.1:8001"
  default_model: "qwen2.5-1.5b"
  default_temperature: 0.7
  default_max_tokens: 512
```

## 🛠️ Development

### Project Requirements

- Python 3.10+
- Redis 6.0+
- Docker (for actual rollouts)
- GPU with CUDA (for vLLM)
- Local Qwen 2.5 1.5B model

### Running Individual Services

```bash
# Activate venv
source venv/bin/activate

# Start Redis
redis-server --daemonize yes

# Start vLLM (terminal 1)
bash start_llm_server.sh

# Start Worker Router (terminal 2)
bash start_worker_router.sh
```

### Testing Individual Components

```python
# Test Redis connection
from worker_router.redis_client import RedisClient
redis = RedisClient("localhost", 6379)
print(redis.ping())  # Should print True

# Test LLM client
from ez_llm_server.client import InferenceEngineClientWrapper
client = InferenceEngineClientWrapper(
    endpoint="http://127.0.0.1:8001",
    model_name="qwen2.5-1.5b"
)
# Use client.generate() for inference
```

## 📊 Monitoring

### Redis State

```bash
# Connect to Redis CLI
redis-cli

# List all keys
KEYS *

# Check worker status
HGETALL worker:{worker_id}

# Check task status
HGETALL task:{task_id}

# Get result
GET result:{task_id}
```

### Worker Processes

```bash
# List worker processes
ps aux | grep worker_unit

# Kill specific worker
pkill -f "worker_unit.*worker-id"
```

## 🔍 Troubleshooting

### Redis Connection Error

```bash
# Check if Redis is running
redis-cli ping

# Start Redis
redis-server --daemonize yes
```

### vLLM: Model Not Found

```bash
# Check model path
ls /mnt/e/models/qwen2.5-1.5b

# Update path in start_llm_server.sh if needed
```

### vLLM: CUDA Out of Memory

```bash
# Edit start_llm_server.sh
# Change: --gpu-memory-utilization 0.9
# To: --gpu-memory-utilization 0.7

# Or close other GPU processes
nvidia-smi
kill -9 <PID>
```

### Port Already in Use

```bash
# Find process using port
lsof -i :5000  # Worker Router
lsof -i :8001  # vLLM

# Kill process
kill -9 <PID>
```

## 📚 Documentation

For complete architecture and design details, see:

- `STARTUP_GUIDE.md` - Complete startup guide
- `design/API_INPUT_OUTPUT.md` - Complete API specification
- `design/ARCHITECTURE_VISUAL.md` - Visual architecture diagrams
- `design/WORKER_MANAGEMENT_TECH_SPEC.md` - Technical specifications
- `design/README.md` - Design documentation index
- `ez_llm_server/README.md` - LLM server documentation

## 🚧 Current Status

**Implementation Status**: ✅ Complete (v0.1.0)

- ✅ Worker Router FastAPI server
- ✅ Redis state management
- ✅ Worker subprocess management
- ✅ API endpoints (rollout, workers)
- ✅ File logging
- ✅ vLLM server integration
- ✅ SkyRL-compatible LLM client
- ✅ Demo worker with mocked Docker operations

**TODO for Production**:
- [ ] Replace mocked Docker operations with real docker-py
- [ ] Add authentication (JWT/API keys)
- [ ] Add task retry logic
- [ ] Add worker health monitoring
- [ ] Add metrics/Prometheus integration

## 📞 Support

For issues or questions:
1. Check the logs in `logs/`
2. Review API documentation at http://localhost:5000/docs
3. See `STARTUP_GUIDE.md` for detailed startup instructions
4. See design docs in `design/` directory

---

**Version**: 0.1.0  
**Last Updated**: 2026-03-10  
**Status**: Development ✅
