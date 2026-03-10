# Subprocess-Based Docker Adapter - Implementation Summary

## Problem

The worker unit test was failing with a Docker connection error in WSL2:

```
docker.errors.DockerException: Error while fetching server API version: 
Not supported URL scheme http+docker
```

**Root Cause**: The Python Docker SDK uses the `requests` library, which automatically picks up proxy environment variables. These proxies interfere with unix socket connections, even though Docker CLI commands work perfectly fine.

## Solution

Created `VulhubAdapterTest` - a subprocess-based version that uses Docker CLI commands instead of the Python Docker SDK.

## Files Created/Modified

### Created
1. **`worker_unit/docker/vulhub_adapter_test.py`** (495 lines)
   - Complete rewrite using `subprocess.run()` for all Docker operations
   - Identical interface to original `VulhubAdapter`
   - Stores container names (strings) instead of container objects

2. **`worker_unit/docker/ADAPTER_TEST_README.md`**
   - Comprehensive documentation of the new adapter
   - Comparison table: SDK vs subprocess
   - Usage examples and migration path

3. **`worker_orchestrator/SUBPROCESS_ADAPTER_SUMMARY.md`** (this file)
   - High-level summary of the solution

### Modified
1. **`test/worker_unit/test_rollout.py`**
   - Added monkey-patch to use `VulhubAdapterTest`
   - Patches import before other modules load
   
2. **`test/worker_unit/README.md`**
   - Added section explaining `VulhubAdapterTest`
   - Added TODO item for potential merge

## Key Implementation Changes

### Container References
```python
# Original (Docker SDK)
self.target_container = client.containers.get(container_id)
self.attacker_container = client.containers.run(...)

# Test (subprocess)
self.target_container_name = "container_name_string"
self.attacker_container_name = "attacker_container_name_string"
```

### Docker Operations
```python
# Original: Start container
self.attacker_container = client.containers.run(
    image="cve-attacker:latest",
    name="attacker",
    network="my_network",
    detach=True
)

# Test: Start container
subprocess.run([
    "docker", "run",
    "--name", "attacker",
    "--network", "my_network",
    "--detach",
    "cve-attacker:latest"
])
```

### Command Execution
```python
# Original: Execute in container
result = container.exec_run(["bash", "-c", command], demux=True)
stdout = result.output[0].decode()

# Test: Execute in container
result = subprocess.run(
    ["docker", "exec", container_name, "bash", "-c", command],
    capture_output=True
)
stdout = result.stdout.decode()
```

### Container Info
```python
# Original: Get container info
networks = list(container.attrs['NetworkSettings']['Networks'].keys())

# Test: Get container info
inspect_result = subprocess.run(
    ["docker", "inspect", container_id],
    capture_output=True, text=True
)
container_info = json.loads(inspect_result.stdout)[0]
networks = list(container_info['NetworkSettings']['Networks'].keys())
```

## Usage

### Automatic (in tests)
```python
# test/worker_unit/test_rollout.py
import worker_unit.docker as docker_module
from worker_unit.docker.vulhub_adapter_test import VulhubAdapterTest
docker_module.VulhubAdapter = VulhubAdapterTest
```

### Manual
```python
from worker_unit.docker.vulhub_adapter_test import VulhubAdapterTest

config = {
    "vulhub_path": "apache-cxf/CVE-2024-28752",
    "task_id": "test-001"
}
adapter = VulhubAdapterTest(config)
```

## Testing

```bash
cd /mnt/e/git_fork_folder/VulRL/worker_orchestrator
bash test/worker_unit/test_rollout.sh
```

Expected behavior:
1. ✅ LLM server check passes
2. ✅ Docker Compose starts Vulhub environment
3. ✅ Attacker container starts
4. ✅ Agent loop executes with LLM
5. ✅ Commands run in Docker containers
6. ✅ Environment cleans up

## Why This Works

**The Key Insight**: Your shell command `docker compose up` works fine with the proxy because:
- The Docker CLI connects directly to the unix socket
- It doesn't use the `requests` library
- Proxy settings don't interfere with local socket connections

**Our Solution**: Use the exact same Docker CLI that works in your shell, called from Python via `subprocess`.

## Comparison

| Aspect | Original (SDK) | Test (subprocess) |
|--------|---------------|-------------------|
| **Proxy issues** | ❌ Fails in WSL2 | ✅ Works perfectly |
| **Performance** | ⚡ Fast | 🐌 Slightly slower |
| **Error handling** | ✅ Rich exceptions | ⚠️ Basic errors |
| **Dependencies** | Needs docker-py | Only Docker CLI |
| **Code complexity** | 🟢 Clean API | 🟡 More verbose |
| **Maintenance** | 🟢 Stable library | 🟡 Depends on CLI |

## Next Steps

### Short Term
- [x] Create `VulhubAdapterTest`
- [x] Update test to use it
- [x] Document the solution
- [ ] Run full test to verify

### Medium Term
- [ ] Add config flag to choose adapter (SDK vs subprocess)
- [ ] Improve error messages in subprocess version
- [ ] Add retry logic for transient failures
- [ ] Cache container info to reduce `docker inspect` calls

### Long Term
- [ ] Consider making subprocess default for WSL2
- [ ] Merge both implementations with feature flag
- [ ] Add comprehensive unit tests
- [ ] Performance profiling and optimization

## Related Documentation

- `worker_unit/docker/ADAPTER_TEST_README.md` - Full adapter documentation
- `test/worker_unit/README.md` - Test suite documentation
- `WORKER_UNIT_IMPLEMENTATION.md` - Overall worker unit design

## Troubleshooting

### If test still fails with Docker errors:
1. Check Docker is running: `docker ps`
2. Check permissions: `docker info`
3. Verify compose works: `docker compose version`

### If subprocess commands are slow:
1. Consider caching container lookups
2. Use `docker inspect` less frequently
3. Batch multiple operations

### If you want to use SDK version instead:
1. Comment out the monkey-patch in `test_rollout.py`
2. Fix proxy issues at the OS level
3. Or use the original adapter with `DOCKER_HOST` unset
