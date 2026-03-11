# EzVulRL Generator

HTTP-based generator for VulRL that integrates with SkyRL's training framework.

## Overview

The EzVulRL Generator is a SkyRL-compatible generator that delegates vulnerability exploitation rollouts to a distributed worker pool via HTTP API. It mimics the `mini_swe_agent` pattern but uses Worker Router for task distribution instead of Ray remote actors.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│ SkyRL Training Loop                                         │
│ - Manages training iteration                                │
│ - Provides prompts and environment configs                  │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ calls generator.generate(input_batch)
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ EzVulRLGenerator                                            │
│ - Inherits from SkyRLGymGenerator                          │
│ - Converts SkyRL inputs to HTTP requests                   │
│ - ACTIVE POLLING LOOP (check every 10s)                    │
│ - Converts worker results to SkyRL token format            │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ HTTP POST /api/rollout/execute
                 │ HTTP GET /api/rollout/status/{task_id}
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Worker Router (FastAPI)                                     │
│ - Manages worker pool                                       │
│ - Queues tasks in Redis                                     │
│ - Tracks task status                                        │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │ Redis Queue
                 ▼
┌─────────────────────────────────────────────────────────────┐
│ Worker Unit(s)                                              │
│ - Poll Redis for tasks                                      │
│ - Execute rollout (Docker + LLM)                            │
│ - Push results to Redis                                     │
└─────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. `ez_vulrl_generator.py`
Main generator class that inherits from `SkyRLGymGenerator`.

**Key Methods**:
- `generate()`: Entry point called by SkyRL, processes batch of prompts
- `vulrl_agent_loop()`: Core logic for single rollout execution
- `_convert_trajectory_to_messages()`: Converts worker trajectory to SkyRL message format
- `_get_loss_mask()`: Generates loss mask for training

**Key Features**:
- Submits rollout via HTTP to Worker Router
- Active polling loop to wait for completion
- Converts worker trajectory format to SkyRL token IDs
- Handles failures gracefully (returns None for failed rollouts)

### 2. `worker_router_client.py`
HTTP client for Worker Router API with active polling.

**Key Methods**:
- `submit_rollout()`: Submit a rollout request, returns task_id
- `get_rollout_status()`: Get current status of a task
- `wait_for_rollout()`: **ACTIVE POLLING LOOP** - polls status until completion
- `check_workers_health()`: Check worker availability

**Polling Mechanism**:
```python
while True:
    result = await get_rollout_status(task_id)
    
    if result.status == "completed":
        return result
    elif result.status == "failed":
        raise RuntimeError(...)
    
    await asyncio.sleep(poll_interval)  # Wait 10 seconds
```

## Usage

### Standalone (for testing)

```python
import asyncio
from ez_generator import EzVulRLGenerator

# Create generator with mock configs
generator = EzVulRLGenerator(
    generator_cfg=mock_config,
    skyrl_gym_cfg=mock_skyrl_config,
    inference_engine_client=mock_client,  # Will be ignored
    tokenizer=tokenizer,
    model_name="qwen2.5-1.5b",
    worker_router_url="http://localhost:5000",
    llm_endpoint="http://localhost:8001",
    llm_model_name="qwen2.5-1.5b",
    polling_config={
        "timeout": 600.0,
        "poll_interval": 10.0,
        "verbose": True,
    }
)

# Call agent loop directly
result = await generator.vulrl_agent_loop(
    prompt="exploit the target",
    env_extras={"cve_id": "CVE-2024-28752", "vulhub_path": "apache-cxf/CVE-2024-28752"},
    max_tokens=512,
    max_input_length=2048,
    sampling_params={"temperature": 0.7},
    trajectory_id="test_001",
    batch_metadata=mock_metadata,
)
```

### Integration with SkyRL

Replace the generator in SkyRL's training config:

```python
# In your SkyRL training script
from ez_generator import EzVulRLGenerator

generator = EzVulRLGenerator(
    generator_cfg=config.generator,
    skyrl_gym_cfg=config.skyrl_gym,
    inference_engine_client=inference_engine_client,  # Will be ignored
    tokenizer=tokenizer,
    model_name=model_name,
    worker_router_url="http://localhost:5000",
    llm_endpoint="http://localhost:8001",
    llm_model_name="qwen2.5-1.5b",
)

# Use in training loop (same as any SkyRL generator)
for epoch in range(num_epochs):
    input_batch = get_training_batch()
    output = await generator.generate(input_batch)
    # ... continue with training ...
```

## Configuration

### Polling Configuration
```python
polling_config = {
    "timeout": 600.0,        # Maximum time to wait per rollout (10 minutes)
    "poll_interval": 10.0,   # Check status every 10 seconds
    "verbose": True,         # Print polling progress
}
```

Adjust based on your needs:
- **Fast testing**: `poll_interval=2.0` (check every 2 seconds)
- **Production**: `poll_interval=10.0` (check every 10 seconds)
- **Long tasks**: `timeout=1800.0` (30 minutes)

### Generator Configuration
The generator accepts all standard SkyRL generator configs:
- `sampling_params`: Temperature, max_tokens, etc.
- `max_input_length`: Maximum context length
- `backend`: LLM backend type (vllm, etc.)

## Data Flow

### Input Flow (SkyRL → Worker)
```
SkyRL Input:
  prompts: ["exploit the target"]
  env_extras: [{"cve_id": "CVE-2024-28752", "vulhub_path": "..."}]
  trajectory_ids: ["traj_001"]

↓ Convert to RolloutRequest

HTTP Request:
  POST /api/rollout/execute
  {
    "cve_id": "CVE-2024-28752",
    "vulhub_path": "apache-cxf/CVE-2024-28752",
    "prompt": "exploit the target",
    "llm_endpoint": "http://localhost:8001",
    "model_name": "qwen2.5-1.5b",
    "max_steps": 10,
    ...
  }

↓ Worker Router assigns to Worker Unit

Worker executes rollout
```

### Output Flow (Worker → SkyRL)
```
Worker Result:
  trajectory: [
    {step: 0, action: "ls", observation: "file1 file2", reward: 0.0, done: False},
    {step: 1, action: "cat file1", observation: "...", reward: 0.0, done: False},
    ...
  ]

↓ Poll until completed

HTTP Response:
  GET /api/rollout/status/{task_id}
  {
    "status": "completed",
    "reward": 0.0,
    "trajectory": [...],
    "success": False,
    ...
  }

↓ Convert to SkyRL format

SkyRL Output:
  response_ids: [123, 456, 789, ...]  # Tokenized actions
  rewards: [0.0]
  loss_masks: [1, 1, 0, 0, 1, ...]    # 1=train, 0=ignore
  prompt_ids: [42, 43, 44, ...]        # Tokenized prompt
```

## Testing

Run the test suite:
```bash
cd worker_orchestrator
bash test/ez_generator/test_generator.sh
```

See `test/ez_generator/README.md` for detailed test documentation.

## Error Handling

### Network Errors
- Automatic retry with exponential backoff (up to 3 retries)
- Raises `RuntimeError` after max retries

### Timeouts
- Configurable timeout per rollout
- Raises `TimeoutError` if not completed within timeout

### Failed Rollouts
- Returns `None` for failed trajectories
- SkyRL filters out `None` entries automatically
- Raises error if ALL trajectories fail

### Worker Unavailability
- Task is queued if no workers available
- Polling loop waits for worker to become available

## Comparison with Ray-based Generators

| Aspect | EzVulRL (HTTP) | mini_swe_agent (Ray) |
|--------|----------------|----------------------|
| **Execution** | HTTP API + Worker Pool | Ray remote actors |
| **Scaling** | Add more worker processes | Ray manages resources |
| **Latency** | ~10s overhead (polling) | ~0.1s (local) |
| **Monitoring** | Worker Router API | Ray dashboard |
| **Deployment** | Distributed (any network) | Single machine / cluster |
| **LLM** | Separate ez_llm_server | InferenceEngineClient |

## Advantages

1. **Distributed Execution**: Workers can run on different machines
2. **Easy Scaling**: Just start more worker processes
3. **Monitoring**: REST API for status checks
4. **Fault Tolerance**: Workers can crash without affecting generator
5. **SkyRL Compatible**: Drop-in replacement for other generators

## Limitations

1. **Latency**: HTTP polling adds ~10s overhead per rollout
2. **Network Dependency**: Requires reliable network connection
3. **Complexity**: More moving parts (Worker Router, Redis, Workers)

## Next Steps

1. **Full SkyRL Integration**: Test in actual training loop
2. **Performance Optimization**: Reduce polling overhead
3. **Batch Processing**: Support multiple rollouts per HTTP request
4. **Error Recovery**: Handle worker crashes gracefully
5. **Metrics**: Track latency, success rate, worker utilization
