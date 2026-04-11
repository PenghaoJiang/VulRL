# VulhubAdapterTest - Subprocess-Based Docker Adapter

## Purpose

`VulhubAdapterTest` is a subprocess-based version of `VulhubAdapter` that uses Docker CLI commands instead of the Python Docker SDK. This avoids proxy-related connection issues in WSL2 environments.

## Problem

In WSL2, the Python Docker SDK (`docker-py`) can fail with errors like:
```
docker.errors.DockerException: Error while fetching server API version: 
Not supported URL scheme http+docker
```

This happens because:
1. The `docker-py` library uses the `requests` library internally
2. `requests` automatically picks up proxy environment variables (`HTTP_PROXY`, etc.)
3. These proxies interfere with unix socket connections (`unix:///var/run/docker.sock`)
4. Even though the Docker CLI works fine with the same proxy settings

## Solution

`VulhubAdapterTest` replaces all Python Docker SDK calls with subprocess commands:

| Original (Docker SDK) | VulhubAdapterTest (subprocess) |
|----------------------|-------------------------------|
| `docker.from_env()` | None (no client needed) |
| `client.containers.get(id)` | `subprocess.run(["docker", "inspect", id])` |
| `container.exec_run(cmd)` | `subprocess.run(["docker", "exec", name, ...])` |
| `client.containers.run(...)` | `subprocess.run(["docker", "run", ...])` |
| `client.images.build(...)` | `subprocess.run(["docker", "build", ...])` |
| `container.stop()` | `subprocess.run(["docker", "stop", name])` |

## Key Differences

### Container References
- **Original**: Stores `Container` objects (`self.target_container`, `self.attacker_container`)
- **Test**: Stores container names as strings (`self.target_container_name`, `self.attacker_container_name`)

### Command Execution
- **Original**: Uses `container.exec_run(["bash", "-c", command])`
- **Test**: Uses `subprocess.run(["docker", "exec", container_name, "bash", "-c", command])`

### HTTP Requests (in container)
- **Original**: Uses `container.exec_run()` with curl
- **Test**: Uses `docker exec` with curl (same approach, different implementation)

### Container Discovery
- **Original**: Uses `client.containers.get(id)` and accesses `.attrs`
- **Test**: Uses `docker inspect` and parses JSON output

## Usage

### In Tests (Automatic)

The test script automatically patches the import:

```python
# In test/worker_unit/test_rollout.py
import worker_unit.docker as docker_module
from worker_unit.docker.vulhub_adapter_test import VulhubAdapterTest
docker_module.VulhubAdapter = VulhubAdapterTest
```

### Manual Usage

```python
from worker_unit.docker.vulhub_adapter_test import VulhubAdapterTest

config = {
    "vulhub_path": "apache-cxf/CVE-2024-28752",
    "vulhub_base_path": "/mnt/e/git_fork_folder/VulRL/benchmark/vulhub",
    "task_id": "test-001"
}

adapter = VulhubAdapterTest(config)
observation, info = adapter.setup()
# ... use adapter ...
adapter.teardown()
```

## Advantages

✅ **Works with proxies** - Uses same Docker CLI that works in your shell
✅ **No dependency issues** - Doesn't need special Python Docker SDK configuration
✅ **Identical interface** - Drop-in replacement for `VulhubAdapter`
✅ **No code changes needed** - Just patch the import in tests
✅ **WSL2 compatible** - Handles WSL2 networking quirks

## Disadvantages

⚠️ **Slightly slower** - Spawns subprocess for each Docker command
⚠️ **More brittle** - Depends on Docker CLI output format
⚠️ **Less error handling** - Subprocess errors are less structured

## Testing

Run the test with:

```bash
cd /mnt/e/git_fork_folder/VulRL/worker_orchestrator
bash test/worker_unit/test_rollout.sh
```

The test will:
1. Check LLM server is running
2. Start a Vulhub environment (apache-cxf/CVE-2024-28752)
3. Run agent loop with LLM
4. Execute commands in Docker containers
5. Clean up

## Implementation Details

### JSON Parsing
All `docker inspect` output is parsed as JSON:
```python
inspect_result = subprocess.run(
    ["docker", "inspect", container_id],
    capture_output=True, text=True, timeout=10
)
container_info = json.loads(inspect_result.stdout)[0]
container_name = container_info['Name'].lstrip('/')
```

### Command Execution
All commands use `subprocess.run()` with timeouts:
```python
exec_result = subprocess.run(
    ["docker", "exec", self.attacker_container_name, "bash", "-c", command],
    capture_output=True,
    timeout=30
)
```

### Error Handling
Errors are caught and logged, but not as detailed as the SDK version:
```python
try:
    result = subprocess.run([...], check=True)
except subprocess.CalledProcessError as e:
    print(f"Command failed: {e}")
```

## Future Work

- [ ] Add more comprehensive error messages
- [ ] Cache container info to reduce `docker inspect` calls
- [ ] Add retry logic for transient failures
- [ ] Consider merging back into main adapter with feature flag
- [ ] Add unit tests for individual methods

## Migration Path

If this proves stable, we can:
1. Add a config flag `use_subprocess_docker = True`
2. Merge both implementations into one adapter
3. Make subprocess the default for WSL2 environments
4. Keep SDK version for non-WSL Linux

## Related Files

- `worker_unit/docker/vulhub_adapter.py` - Original adapter (uses Docker SDK)
- `worker_unit/docker/vulhub_adapter_test.py` - Subprocess adapter (this implementation)
- `test/worker_unit/test_rollout.py` - Test that uses this adapter
- `worker_unit/env/security_env.py` - Environment that imports VulhubAdapter
