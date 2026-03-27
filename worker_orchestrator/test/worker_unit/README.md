# Worker Unit Tests

Test suite for the VulRL Worker Unit, which executes vulnerability exploitation rollouts using Docker environments and LLM-based agents.

## Test Files

### `test_rollout.py`
Standalone Python test for the rollout executor. Tests the complete flow:
1. Initialize LLM client
2. Setup Docker environment (Vulhub)
3. Run agent loop (LLM + environment interaction)
4. Collect trajectory and rewards
5. Clean up environment

### `test_rollout.sh`
Bash script to run the test with proper setup:
- Activates Python virtual environment
- Checks if LLM server is running
- Runs the Python test script

## Test Case

**CVE**: apache-cxf/CVE-2024-28752  
**Vulhub Path**: `/mnt/e/git_fork_folder/VulRL/benchmark/vulhub/apache-cxf/CVE-2024-28752`  
**Prompt**: "write a hello world script at /tmp/workspace/"  
**Max Steps**: 5  
**LLM**: http://127.0.0.1:8001 (qwen2.5-1.5b)

## Prerequisites

1. **Virtual Environment**: Set up the worker_orchestrator venv
   ```bash
   cd /mnt/e/git_fork_folder/VulRL/worker_orchestrator
   bash setup.sh
   ```

2. **LLM Server**: Start the vLLM server
   ```bash
   cd /mnt/e/git_fork_folder/VulRL/worker_orchestrator
   bash start_llm_server.sh
   ```

3. **Docker**: Ensure Docker is running and accessible

4. **Vulhub Benchmark**: Ensure the Vulhub case exists at:
   `/mnt/e/git_fork_folder/VulRL/benchmark/vulhub/apache-cxf/CVE-2024-28752`

## Running Tests

### Quick Test (Bash Script)
```bash
cd /mnt/e/git_fork_folder/VulRL/worker_orchestrator
bash test/worker_unit/test_rollout.sh
```

### Manual Test (Python)
```bash
cd /mnt/e/git_fork_folder/VulRL/worker_orchestrator
source venv/bin/activate
python -m test.worker_unit.test_rollout
```

## Expected Output

```
======================================================================
Testing Worker Unit Rollout Executor
======================================================================

✓ LLM server is running

Running worker unit test...

======================================================================
Worker Unit Rollout Test
======================================================================

Test Configuration:
  CVE ID: CVE-2024-28752
  Vulhub Path: apache-cxf/CVE-2024-28752
  Prompt: write a hello world script at /tmp/workspace/
  Max Steps: 5
  LLM: http://127.0.0.1:8001

Executing rollout...

======================================================================
Starting Rollout: CVE-2024-28752_1234567890
======================================================================
...
[Agent loop interaction]
...
======================================================================
Rollout Completed Successfully
======================================================================
Duration: 45.23s
Steps: 3
Reward: 0.0
Success: False

✓ Rollout completed successfully!
✓ Test completed!
```

## Troubleshooting

### "LLM server not running"
Start the LLM server:
```bash
bash start_llm_server.sh
```

### "Vulhub path not found"
Check the path exists:
```bash
ls /mnt/e/git_fork_folder/VulRL/benchmark/vulhub/apache-cxf/CVE-2024-28752
```

### "Docker connection error"
Ensure Docker is running:
```bash
docker ps
```

### "Failed to start Vulhub"
Check Docker Compose:
```bash
cd /mnt/e/git_fork_folder/VulRL/benchmark/vulhub/apache-cxf/CVE-2024-28752
docker compose ps
```

## Components Tested

1. **RolloutExecutor**: Main orchestrator for complete rollout
2. **SecurityEnv**: Gymnasium-compliant environment wrapper
3. **VulhubAdapter**: Docker Compose + attacker container management
4. **Agent Loop**: LLM-environment interaction (simplified from SkyRL)
5. **InferenceEngineClientWrapper**: LLM client (OpenAI-compatible)
6. **RewardCalculator**: Reward computation (currently returns 0.0)

## VulhubAdapterTest

**Important**: This test uses `VulhubAdapterTest` instead of the original `VulhubAdapter`.

`VulhubAdapterTest` is a subprocess-based adapter that:
- Uses Docker CLI commands (`docker exec`, `docker inspect`, etc.)
- Avoids Python Docker SDK proxy issues in WSL2
- Has identical interface to the original adapter
- Automatically patched in `test_rollout.py`

See `worker_unit/docker/ADAPTER_TEST_README.md` for full details.

## TODO

- [ ] Implement actual reward calculation
- [ ] Add tests for error handling
- [ ] Add tests for timeout scenarios
- [ ] Add tests with different Vulhub cases
- [ ] Add integration test with Worker Router + Redis
- [ ] Consider merging VulhubAdapterTest into main adapter with feature flag