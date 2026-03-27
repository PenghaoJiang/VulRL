# Worker Unit

Self-contained worker unit for executing VulRL vulnerability exploitation rollouts.

## Architecture

```
worker_unit/
├── __init__.py                 # Package init
├── main.py                     # Redis polling entry point
├── rollout_executor.py         # Core: Execute complete rollout
├── agent_loop.py               # Simplified SkyRL agent loop
│
├── docker/                     # Docker environment adapters
│   ├── __init__.py
│   ├── env_types.py            # StandardAction, StandardObservation, StandardInfo
│   ├── env_adapter.py          # BaseEnvAdapter (abstract base class)
│   └── vulhub_adapter.py       # VulhubAdapter (Docker Compose + attacker container)
│
├── env/                        # Environment management
│   ├── __init__.py
│   └── security_env.py         # SecurityEnv (Gymnasium-compliant)
│
└── reward/                     # Reward calculation
    ├── __init__.py
    └── reward_calculator.py    # RewardCalculator (TODO: implement logic)
```

## Components

### Core

- **`main.py`**: Entry point for worker process
  - Polls Redis for rollout tasks
  - Delegates to RolloutExecutor
  - Stores results back to Redis

- **`rollout_executor.py`**: Orchestrates complete rollout
  - Initializes LLM client (InferenceEngineClientWrapper)
  - Sets up environment (SecurityEnv)
  - Runs agent loop
  - Computes rewards
  - Returns RolloutResult

- **`agent_loop.py`**: LLM-environment interaction loop
  - Simplified from SkyRL's skyrl_gym_generator.py
  - String-based (no tokenization)
  - Generates actions via LLM
  - Executes in environment
  - Collects trajectory

### Docker Adapters

- **`docker/env_types.py`**: Standard data structures
  - `ActionType`: BASH, HTTP_REQUEST
  - `StandardAction`: Action representation
  - `StandardObservation`: Observation representation
  - `StandardInfo`: Metadata

- **`docker/env_adapter.py`**: Abstract base adapter
  - `setup()`: Start Docker environment
  - `teardown()`: Clean up
  - `reset()`: Reset to initial state
  - `step()`: Execute action

- **`docker/vulhub_adapter.py`**: Vulhub implementation
  - Manages Docker Compose
  - Spawns attacker container
  - Executes bash/HTTP commands
  - Returns standardized observations

### Environment

- **`env/security_env.py`**: Gymnasium-compliant environment
  - Wraps VulhubAdapter
  - Provides simple interface: reset(), step(), close()
  - Tracks trajectory
  - Manages episode state

### Reward

- **`reward/reward_calculator.py`**: Reward computation
  - `compute_step_reward()`: Per-step rewards (TODO)
  - `compute_episode_reward()`: Final episode reward (TODO)
  - Currently returns 0.0

## Dependencies

### From worker_orchestrator
- `worker_router.models`: RolloutRequest, RolloutResult, TrajectoryStep
- `worker_router.redis_client`: RedisClient
- `worker_router.config`: Config
- `ez_llm_server.client`: InferenceEngineClientWrapper

### External
- `docker`: Docker Python SDK
- `subprocess`: Docker Compose management
- `asyncio`: Async execution

## Usage

### Standalone (via Redis)

```bash
# Start worker
python -m worker_unit.main --worker-id worker_001
```

### Testing

```bash
# Run standalone test
cd /mnt/e/git_fork_folder/VulRL/worker_orchestrator
bash test/worker_unit/test_rollout.sh
```

See `test/worker_unit/README.md` for detailed test documentation.

## Flow

1. **Initialize** (main.py):
   - Connect to Redis
   - Wait for rollout tasks

2. **Receive Task** (main.py):
   - Pop task from Redis queue
   - Parse RolloutRequest

3. **Execute Rollout** (rollout_executor.py):
   - Initialize LLM client
   - Setup Docker environment
   - Reset environment → initial observation
   - Run agent loop:
     - LLM generates action
     - Execute in environment
     - Get observation
     - Store trajectory step
     - Repeat until done or max_steps
   - Compute rewards
   - Clean up environment

4. **Return Result** (main.py):
   - Store RolloutResult in Redis
   - Update worker status
   - Continue polling

## Configuration

Environment config passed to SecurityEnv:

```python
{
    "task_type": "vulhub",
    "task_id": "CVE-XXXX-XXXXX",
    "vulhub_path": "software/CVE-XXXX-XXXXX",
    "max_steps": 30,
    "backend_config": {
        "vulhub_path": "software/CVE-XXXX-XXXXX",
        "vulhub_base_path": "/mnt/e/git_fork_folder/VulRL/benchmark/vulhub"
    },
    "target_host": "target",
    "target_port": 80,
    "target_protocol": "http",
    "timeout": 30
}
```

## TODO

### High Priority
- [ ] Implement actual reward calculation logic
- [ ] Add error recovery mechanisms
- [ ] Add timeout handling
- [ ] Add progress reporting to Redis

### Medium Priority
- [ ] Support for multi-agent (PoC gen + verification)
- [ ] Support for different Docker backends (CVEbench, Xbow)
- [ ] Optimize Docker cleanup
- [ ] Add metrics collection

### Low Priority
- [ ] Support for HTTP_REQUEST action type
- [ ] Add action parsing from LLM output (structured actions)
- [ ] Add visualization of trajectories
- [ ] Add debugging tools

## Notes

- All code is self-contained (copied from vulrl_inside_skyrl, not imported)
- Uses same LLM interface as SkyRL (InferenceEngineClientWrapper)
- Simplified from SkyRL (no tokenization, loss masks, logprobs)
- Docker path is WSL-compatible: `/mnt/e/git_fork_folder/VulRL/benchmark/vulhub`
