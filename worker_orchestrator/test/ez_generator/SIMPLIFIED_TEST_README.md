# Simplified EZ_Generator Test

**Purpose**: Test core Worker Router functionality without SkyRL dependencies.

---

## 🎯 What This Tests

### ✅ Core Functionality (No SkyRL Required)
1. **HTTP Client** - WorkerRouterClient communication
2. **Auto-Scaling** - Automatic worker spawning when needed
3. **Active Polling** - Poll status every 5 seconds until completion
4. **Rollout Execution** - Full rollout through Worker Unit
5. **Result Retrieval** - Get trajectory, reward, status

### ❌ Not Tested (Requires SkyRL)
- Full `EzVulRLGenerator` class
- Token ID generation
- Loss mask generation
- Integration with SkyRL training loop

---

## 🚀 Usage

### Quick Test
```bash
cd worker_orchestrator/test/ez_generator
bash test_simple.sh
```

### What You'll See
```
========================================================================
Simplified EZ_Generator Test (No SkyRL Dependencies)
========================================================================

1. Checking initial worker status...
   Workers: 0 total, 0 active, 0 idle
   ⚠ No workers running - auto-scaling will be triggered!

2. Building rollout request...
   CVE: CVE-2024-28752
   Prompt: write a hello world script at /tmp/workspace/
   Max steps: 3

3. Submitting rollout request...
   ✓ Task submitted: a7f3c9d2-4b1e-4a8f-9c3e-1d2e3f4a5b6c

4. Checking if worker was auto-spawned...
   Workers now: 1 total, 1 active
   ✓ Auto-scaling triggered successfully!

5. Polling for completion (active polling mechanism)...
   Poll interval: 5 seconds
   Timeout: 120 seconds

[WorkerRouterClient] Waiting for task a7f3c9d2-4b1e-4a8f-9c3e-1d2e3f4a5b6c
[WorkerRouterClient] Poll #1 (0.2s): status=running
[WorkerRouterClient] Poll #2 (5.3s): status=running
[WorkerRouterClient] Poll #3 (10.4s): status=completed
[WorkerRouterClient] ✓ Task completed after 10.4s

========================================================================
Test Results
========================================================================
Status: completed
Worker ID: auto_a7f3c9d2
Reward: 0.0
Success: False
Duration: 10.38s
Steps: 3

✓ Test Completed Successfully!

Summary:
  ✓ HTTP client working
  ✓ Auto-scaling working (worker spawned)
  ✓ Active polling mechanism working
  ✓ Result retrieval working
  ✓ End-to-end flow successful
```

---

## 📊 Test Flow

```
test_simple.py
    ↓
1. Check workers (0 active)
    ↓
2. Submit rollout → Worker Router
    ↓
3. Worker Router: No workers → Auto-spawn
    ↓
4. Check workers (1 active - auto_XXXXXXXX)
    ↓
5. Poll every 5s: GET /api/rollout/status/{task_id}
    ↓
6. Worker completes → Return result
    ↓
7. Display trajectory, reward, etc.
    ↓
✓ Success!
```

---

## 🔑 Key Differences from Full Test

| Aspect | Full Test (`test_generator.py`) | Simplified Test (`test_simple.py`) |
|--------|----------------------------------|-------------------------------------|
| **Dependencies** | Requires SkyRL + all deps | Only `aiohttp` + `pydantic` |
| **What it tests** | Full generator class | HTTP API + Auto-scaling |
| **Import chain** | Deep (SkyRL → skyrl_gym → ...) | Shallow (only WorkerRouterClient) |
| **Token generation** | Yes (needs tokenizer) | No (just HTTP communication) |
| **Loss masks** | Yes (for training) | No (not needed) |
| **Purpose** | SkyRL integration readiness | Infrastructure validation |

---

## 🎯 When to Use Each Test

### Use Simplified Test (`test_simple.sh`)
- ✅ Quick validation after code changes
- ✅ Testing auto-scaling feature
- ✅ Testing active polling mechanism
- ✅ CI/CD pipelines (fewer dependencies)
- ✅ Development iterations

### Use Full Test (`test_generator.sh`)
- ✅ Final SkyRL integration testing
- ✅ Validating tokenization logic
- ✅ Verifying training compatibility
- ✅ Pre-production validation

---

## 📦 Dependencies

### Simplified Test Requires
```
✓ aiohttp (HTTP client)
✓ pydantic (models)
✓ Worker Router running
✓ LLM server running
✓ Redis running
```

### Full Test Additionally Requires
```
✗ omegaconf
✗ SkyRL (skyrl_train)
✗ skyrl_gym
✗ torch/transformers (tokenizer)
```

---

## ✅ Prerequisites

```bash
# 1. Worker Router
cd worker_orchestrator
bash start_worker_router.sh

# 2. LLM Server
bash start_llm_server.sh

# 3. Redis
sudo systemctl start redis

# That's it! Workers auto-spawn during test.
```

---

## 🔍 What Gets Validated

### ✅ HTTP Communication
- Client can connect to Worker Router
- POST /api/rollout/execute works
- GET /api/rollout/status/{task_id} works
- Response parsing works

### ✅ Auto-Scaling
- Worker Router detects no workers
- Spawns new worker automatically
- Worker registers in Redis
- Task gets assigned to new worker

### ✅ Active Polling
- Client polls every 5 seconds
- Status changes detected (queued → running → completed)
- Timeout handling works
- Result retrieval works

### ✅ End-to-End
- Request → Worker spawn → Execution → Result
- Full rollout completes successfully
- Trajectory returned correctly
- Reward calculated (even if 0)

---

## 🐛 Troubleshooting

### Test fails with "Connection refused"
```bash
# Check Worker Router is running
curl http://localhost:5000/health

# If not running:
cd worker_orchestrator
bash start_worker_router.sh
```

### Test times out
```bash
# Check worker logs
tail -f worker_orchestrator/logs/worker_auto_*.log

# Check Docker is running
docker ps

# Check LLM server is working
curl http://localhost:8001/health
```

### Auto-scaling doesn't work
```bash
# Check Worker Router logs
tail -f worker_orchestrator/logs/worker_router.log

# Look for:
# "[AutoScale] Spawned new worker: auto_XXXXXXXX"
```

---

## 📝 Example Output

**Success:**
```
✓ HTTP client working
✓ Auto-scaling working (worker spawned)
✓ Active polling mechanism working
✓ Result retrieval working
✓ End-to-end flow successful
```

**Failure (Worker Router down):**
```
✗ Worker Router is not running
Start with: cd worker_orchestrator && bash start_worker_router.sh
```

---

## 🎓 Summary

**The simplified test validates that:**
- ✅ Worker Router HTTP API works
- ✅ Auto-scaling spawns workers automatically
- ✅ Active polling retrieves results correctly
- ✅ Full rollout execution succeeds

**Without needing:**
- ❌ SkyRL dependencies
- ❌ Tokenizer setup
- ❌ Training pipeline
- ❌ Manual worker startup

**Perfect for rapid development and CI/CD!** 🚀
