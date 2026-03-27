# Worker Router API Test Scripts

Simple bash scripts to test Worker Router API endpoints.

## 📁 Scripts

| Script | Endpoint | Method | Description |
|--------|----------|--------|-------------|
| `_.sh` | `/` | GET | Root endpoint - service info |
| `_health.sh` | `/health` | GET | Health check |
| `_api_rollout_execute.sh` | `/api/rollout/execute` | POST | Submit rollout task |
| `_api_rollout_status_{task_id}.sh` | `/api/rollout/status/{task_id}` | GET | Get task status/result |
| `_api_workers_status.sh` | `/api/workers/status` | GET | Get all workers status |
| `_api_workers_{worker_id}_shutdown.sh` | `/api/workers/{worker_id}/shutdown` | POST | Shutdown specific worker |

## 🚀 Usage

### 1. Make scripts executable (Linux/Mac)

```bash
chmod +x *.sh
```

### 2. Run tests

**Simple endpoints (no parameters):**

```bash
# Test root endpoint
./_.sh

# Test health check
./_health.sh

# Submit a rollout task
./_api_rollout_execute.sh

# Get workers status
./_api_workers_status.sh
```

**Endpoints with parameters:**

```bash
# Get rollout status (with task_id parameter)
./_api_rollout_status_{task_id}.sh <task_id>
# Example:
./_api_rollout_status_{task_id}.sh 550e8400-e29b-41d4-a716-446655440000

# Shutdown worker (with worker_id parameter)
./_api_workers_{worker_id}_shutdown.sh <worker_id>
# Example:
./_api_workers_{worker_id}_shutdown.sh worker-abc123
```

## 📝 Example Workflow

```bash
# 1. Check service is running
./_health.sh

# 2. Submit a rollout task
./_api_rollout_execute.sh
# Response: {"task_id": "abc-123", "status": "running", ...}

# 3. Check task status (replace with actual task_id from step 2)
./_api_rollout_status_{task_id}.sh abc-123

# 4. Check workers
./_api_workers_status.sh

# 5. Shutdown specific worker (replace with actual worker_id from step 4)
./_api_workers_{worker_id}_shutdown.sh worker-abc123
```

## 🔧 Configuration

All scripts use `http://localhost:5000` as the base URL. To change:

1. Edit each script
2. Replace `localhost:5000` with your server address

## 📊 Example Responses

### Root (`/`)
```json
{
  "service": "VulRL Worker Router",
  "version": "0.1.0",
  "status": "running"
}
```

### Health Check (`/health`)
```json
{
  "status": "healthy",
  "redis": true
}
```

### Submit Rollout (`/api/rollout/execute`)
```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "worker_id": "worker-abc123",
  "queued_at": 1709978400.0,
  "estimated_duration": null
}
```

### Workers Status (`/api/workers/status`)
```json
{
  "workers": [
    {
      "worker_id": "worker-abc123",
      "status": "busy",
      "pid": 12345,
      "started_at": 1709978000.0,
      "current_task": "550e8400-e29b-41d4-a716-446655440000",
      "tasks_completed": 0,
      "tasks_failed": 0,
      "average_duration": null
    }
  ],
  "total": 1,
  "active": 1,
  "idle": 0,
  "busy": 1,
  "dead": 0,
  "queue_length": 0
}
```

## 🐛 Troubleshooting

### curl: command not found

Install curl:
```bash
# Ubuntu/Debian
sudo apt-get install curl

# macOS (usually pre-installed)
brew install curl

# Windows
# Use Git Bash or WSL
```

### Connection refused

1. Check if Worker Router is running:
   ```bash
   # In worker_orchestrator directory
   uvicorn worker_router.app:app --host 0.0.0.0 --port 5000
   ```

2. Check if Redis is running:
   ```bash
   redis-cli ping
   ```

### Permission denied (Linux/Mac)

Make scripts executable:
```bash
chmod +x *.sh
```

---

**Note**: These scripts do not assert results. They simply trigger API calls for easy testing. Check the responses manually or view logs in `../../logs/worker_router.log`.
