# EzVulRL Generator Tests

Test suite for the EzVulRL Generator, which delegates rollout execution to Worker Router API.

## Overview

The EzVulRL Generator is a SkyRL-compatible generator that:
1. Inherits from `SkyRLGymGenerator` for seamless SkyRL integration
2. Delegates rollout execution to Worker Router via HTTP API
3. Uses active polling to wait for worker units to complete tasks
4. Converts worker trajectory format to SkyRL's expected token format

## Architecture

```
SkyRL Training → EzVulRLGenerator → HTTP API → Worker Router → Worker Unit
                        ↓
                   Active Polling Loop
                   (Check status every 10s)
```

## Test Structure

### Test 1: Worker Router Client
- Tests direct HTTP communication with Worker Router
- Verifies health checks and worker status
- Submits a rollout and polls until completion
- Validates the returned trajectory format

### Test 2: Generator Mock
- Tests the generator's SkyRL interface
- Mocks tokenizer and configs
- Calls `vulrl_agent_loop()` directly
- Validates output format (response_ids, reward, loss_mask, etc.)

## Prerequisites

Before running tests, ensure all services are running:

```bash
# Terminal 1: Redis
sudo systemctl start redis

# Terminal 2: LLM Server
cd worker_orchestrator
bash start_llm_server.sh

# Terminal 3: Worker Router
cd worker_orchestrator
bash start_worker_router.sh

# Terminal 4: Worker Unit
cd worker_orchestrator
bash start_worker.sh --worker-id worker001
```

## Running Tests

### Quick Test
```bash
cd worker_orchestrator
bash test/ez_generator/test_generator.sh
```

### Manual Test
```bash
cd worker_orchestrator
source venv/bin/activate
python test/ez_generator/test_generator.py
```

## Expected Output

```
======================================================================
EzVulRL Generator Test Suite
======================================================================

Test 1: Worker Router Client
======================================================================
1. Checking Worker Router health...
✓ Worker Router is healthy

2. Checking workers status...
✓ Workers: 1 total, 1 active

3. Submitting test rollout...
✓ Task submitted: a7f3c9d2-4b1e-4a8f-9c3e-1d2e3f4a5b6c

4. Waiting for rollout to complete...
[WorkerRouterClient] Waiting for task a7f3c9d2-4b1e-4a8f-9c3e-1d2e3f4a5b6c
[WorkerRouterClient] Timeout: 300.0s, Poll interval: 5.0s
[WorkerRouterClient] Poll #1 (0.2s): status=running
[WorkerRouterClient] Poll #2 (5.3s): status=running
[WorkerRouterClient] Poll #3 (10.4s): status=completed
[WorkerRouterClient] ✓ Task completed after 10.4s

======================================================================
Rollout Result
======================================================================
Status: completed
Reward: 0.0
Success: False
Duration: 10.38s
Steps: 5

✓ Test completed successfully!

======================================================================
Test 2: EzVulRL Generator (Mock SkyRL Interface)
======================================================================
1. Initializing generator...
[EzVulRLGenerator] Initialized
  Worker Router: http://localhost:5000
  LLM Endpoint: http://localhost:8001
  LLM Model: qwen2.5-1.5b
  Polling: timeout=300.0s, interval=5.0s
✓ Generator initialized

2. Testing vulrl_agent_loop...
[EzVulRLGenerator] Submitting rollout: CVE-2024-28752
[EzVulRLGenerator] Task ID: b8e4d1c3-...
[WorkerRouterClient] Waiting for task...
[WorkerRouterClient] ✓ Task completed after 12.1s
[EzVulRLGenerator] Received result: reward=0.0, steps=5

======================================================================
Generator Output
======================================================================
Response IDs length: 234
Reward: 0.0
Stop reason: failed
Loss mask length: 234
Prompt IDs length: 45
✓ Valid output: 234 response tokens, reward=0.0

✓ Test completed successfully!

======================================================================
Test Summary
======================================================================
Test 1 (Client): ✓ PASS
Test 2 (Generator): ✓ PASS

✓ All tests passed!
```

## Configuration

### Polling Configuration
```python
polling_config = {
    "timeout": 300.0,        # 5 minutes max per rollout
    "poll_interval": 5.0,    # Check status every 5 seconds (fast for testing)
    "verbose": True,         # Print polling progress
}
```

For production, use longer intervals:
```python
polling_config = {
    "timeout": 600.0,        # 10 minutes max per rollout
    "poll_interval": 10.0,   # Check status every 10 seconds
    "verbose": False,        # Reduce verbosity
}
```

## Troubleshooting

### Test fails with "Worker Router is not healthy"
- Ensure Worker Router is running: `bash start_worker_router.sh`
- Check logs: `tail -f logs/worker_router.log`

### Test fails with "No active workers available"
- Start at least one worker: `bash start_worker.sh --worker-id worker001`
- Check worker status: `curl http://localhost:5000/api/workers/status`

### Test fails with "LLM server is not running"
- Start LLM server: `bash start_llm_server.sh`
- Check health: `curl http://localhost:8001/health`

### Polling timeout
- Increase `timeout` in polling_config
- Check if worker is actually running the task
- Check worker logs for errors

## Integration with SkyRL

To use this generator in SkyRL training:

```python
from ez_generator import EzVulRLGenerator

generator = EzVulRLGenerator(
    generator_cfg=config.generator,
    skyrl_gym_cfg=config.skyrl_gym,
    inference_engine_client=inference_client,  # Will be ignored
    tokenizer=tokenizer,
    model_name=model_name,
    worker_router_url="http://localhost:5000",
    llm_endpoint="http://localhost:8001",
    llm_model_name="qwen2.5-1.5b",
)

# Use in training loop
output = await generator.generate(input_batch)
```

## Next Steps

1. **Full SkyRL Integration**: Test generator in actual SkyRL training loop
2. **Batch Processing**: Test with multiple rollouts in parallel
3. **Error Handling**: Test timeout, failures, worker crashes
4. **Performance**: Measure latency overhead of HTTP polling
5. **Scaling**: Test with multiple workers and concurrent requests
