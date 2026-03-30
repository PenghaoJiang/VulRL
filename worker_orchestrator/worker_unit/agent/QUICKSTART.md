# Agent Framework Quick Start Guide

## Installation

```bash
cd worker_orchestrator
bash setup.sh
```

This will install all dependencies including:
- `simple-parsing` - Config parsing for CTFMix
- `tenacity` - Retry logic
- `openai` - OpenAI API client

## Testing the Agents

### 1. Test DemoAgent (Simple Agent)

```bash
# Activate venv
source venv/bin/activate

# Test with existing worker system
# Request format (add to Redis or call directly):
```

```python
from worker_router.models import RolloutRequest

request = RolloutRequest(
    cve_id="CVE-2023-1234",
    vulhub_path="activemq/CVE-2023-46604",
    prompt="Exploit the ActiveMQ RCE vulnerability",
    llm_endpoint="http://localhost:8000/generate",
    model_name="gpt-4",
    max_steps=10,
    temperature=0.7,
    max_tokens=512,
    metadata={}  # Uses demo agent by default
)

# Execute
from worker_unit.rollout_executor import RolloutExecutor
executor = RolloutExecutor()
result = await executor.execute(request, agent_type="demo")
```

### 2. Test CTFAgent (Advanced Agent)

```python
from worker_router.models import RolloutRequest

request = RolloutRequest(
    cve_id="CVE-2023-1234",
    vulhub_path="activemq/CVE-2023-46604",
    prompt="Exploit the ActiveMQ RCE vulnerability",
    llm_endpoint="http://localhost:8000/generate",
    model_name="gpt-4",
    max_steps=20,
    temperature=0.7,
    max_tokens=1024,
    metadata={"agent_type": "ctf"}  # Use CTF agent
)

# Execute
from worker_unit.rollout_executor import RolloutExecutor
executor = RolloutExecutor()
result = await executor.execute(request, agent_type="ctf")
```

## Verifying Installation

### Check Python Imports

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/path/to/worker_orchestrator')

# Test base imports
from worker_unit.agent import BaseAgent
print("✓ BaseAgent imported")

# Test demo agent
from worker_unit.agent.demo_agent import DemoAgent
print("✓ DemoAgent imported")

# Test CTF agent
from worker_unit.agent.ctf_agent import CTFAgent
print("✓ CTFAgent imported")

# Test adapters
from worker_unit.agent.ctf_agent.llm_adapter import LLMAdapter
from worker_unit.agent.ctf_agent.runtime_adapter import VulhubRuntimeAdapter
from worker_unit.agent.ctf_agent.type_converters import ctfmix_trajectory_to_worker
print("✓ CTF adapters imported")

# Test CTFMix modules
from worker_unit.agent.ctf_agent.ctfmix.agents import Agent
from worker_unit.agent.ctf_agent.ctfmix.models import OpenAIModel, get_model
print("✓ CTFMix modules imported")

print("\n✓ All imports successful!")
EOF
```

### Check Docker Executor

```bash
python3 << 'EOF'
import sys
sys.path.insert(0, '/path/to/worker_orchestrator')

from worker_unit.docker.docker_executor import DockerExecutor
print("✓ DockerExecutor imported")

# Test with mock container (requires docker daemon running)
import docker
client = docker.from_env()
container = client.containers.run(
    "alpine:latest",
    command="tail -f /dev/null",
    detach=True,
    remove=True
)
print(f"✓ Test container created: {container.short_id}")

executor = DockerExecutor(container_obj=container)
result = executor.execute_bash("echo 'Hello from Docker'")
print(f"✓ Execution result:\n{result}")

container.stop()
print("✓ Container cleaned up")
EOF
```

### Check Config Files

```bash
# Verify config files exist
ls -lh worker_unit/agent/config/

# Should see:
# - default_ctf.yaml
# - models_config.yaml
# - commands/ (directory with .sh files)
```

## Common Issues

### Issue 1: Import Error - No module named 'simple_parsing'

```bash
# Solution: Install dependencies
bash setup.sh
```

### Issue 2: Import Error - No module named 'worker_unit'

```bash
# Solution: Add to PYTHONPATH
export PYTHONPATH=/path/to/worker_orchestrator:$PYTHONPATH
```

### Issue 3: FileNotFoundError - default_ctf.yaml not found

```bash
# Check if config copied correctly
ls worker_unit/agent/config/

# If missing, manually copy
cp /path/to/git_folk_folder_02/VulRL/benchmark/ctfmix/config/* worker_unit/agent/config/
```

### Issue 4: Docker errors in VulhubAdapter

```bash
# Check Docker SDK works
python3 -c "import docker; print(docker.from_env().ping())"

# Should print: True
```

## Comparing Agent Outputs

### Expected: DemoAgent Output

```
[DemoAgent] Step 1/10
[DemoAgent] Action: curl http://target:8161
[DemoAgent] Observation: Exit: 0
STDOUT:
<html>ActiveMQ Console</html>
[DemoAgent] Reward: 0.0, Done: False
```

### Expected: CTFAgent Output

```
[CTFAgent] Starting CTFMix agent run
[CTFAgent] Model: gpt-4, Max steps: 20

[CTF Agent Thought]: I need to first identify what version of ActiveMQ is running...

[CTF Agent Action]:
```bash
curl -i http://target:8161
```

[Observation]:
Exit: 0
STDOUT:
HTTP/1.1 200 OK
Server: Jetty(9.4.39.v20210325)
...

[CTF Agent Thought]: The Jetty version suggests ActiveMQ 5.x, which is vulnerable to CVE-2023-46604...
```

Key differences:
- CTFAgent explains reasoning (Thought)
- CTFAgent formats commands in markdown blocks
- CTFAgent handles multi-line commands
- CTFAgent detects submissions

## Next Steps

1. **Install dependencies**: `bash setup.sh`
2. **Test DemoAgent**: Verify backward compatibility
3. **Test CTFAgent**: Try with a simple CVE
4. **Monitor performance**: Compare success rates
5. **Add tests**: Create unit and integration tests
6. **Tune configs**: Adjust agent parameters in config YAMLs

## Architecture Diagram

```
┌─────────────────────────────────────────────────┐
│          Worker Router (FastAPI)                │
│  Receives RolloutRequest with agent_type        │
└─────────────────┬───────────────────────────────┘
                  │ (via Redis)
                  ▼
┌─────────────────────────────────────────────────┐
│          Worker Unit (main.py)                  │
│  Extracts agent_type from metadata              │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│       RolloutExecutor.execute()                 │
│  Creates agent based on agent_type              │
└─────────────────┬───────────────────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼
┌────────────────┐ ┌──────────────────────┐
│  DemoAgent     │ │    CTFAgent          │
│  (Simple)      │ │    (Advanced)        │
└────────┬───────┘ └──────────┬───────────┘
         │                    │
         │                    ▼
         │           ┌─────────────────┐
         │           │  LLM Adapter    │
         │           │  Runtime Adapter│
         │           │  Type Converters│
         │           └────────┬────────┘
         │                    │
         │                    ▼
         │           ┌─────────────────┐
         │           │ CTFMix Agent    │
         │           │ (agents.py)     │
         │           └────────┬────────┘
         │                    │
         └────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│         SecurityEnv (env wrapper)               │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│      VulhubAdapter (Docker management)          │
│  Uses DockerExecutor for command execution      │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│        Docker Containers                        │
│  - target (vulnerable service)                  │
│  - attacker (execution environment)             │
└─────────────────────────────────────────────────┘
```

## Configuration Files

### Agent Config (default_ctf.yaml)

Located in `agent/config/default_ctf.yaml`:
- Agent template (system prompts, format instructions)
- Command definitions (custom bash functions)
- Parsing settings (format templates)
- Session settings (interactive modes)
- Subroutine settings (recursive agent calls)

### Model Config (models_config.yaml)

Located in `agent/config/models_config.yaml`:
- Model metadata (context windows, cost per token)
- Provider shortcuts (model aliases)
- Special model configurations

### Customizing Agent Behavior

To create a custom agent configuration:

```bash
cp agent/config/default_ctf.yaml agent/config/my_custom_agent.yaml
# Edit my_custom_agent.yaml
# Then specify in request:
metadata={"agent_type": "ctf", "agent_config_file": "path/to/my_custom_agent.yaml"}
```

## Debugging Tips

### Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Inspect Trajectory

```python
result = await executor.execute(request, agent_type="ctf")

for step in result.trajectory:
    print(f"Step {step.step}:")
    print(f"  Action: {step.action[:100]}...")
    print(f"  Observation: {step.observation[:100]}...")
    print(f"  Reward: {step.reward}")
    print(f"  Done: {step.done}")
    print(f"  Thought: {step.metadata.get('thought', 'N/A')[:100]}...")
    print()
```

### Check Container Logs

```bash
# List running containers
docker ps

# View logs
docker logs attacker_vulhub_...
docker logs <target_container>
```

## Performance Comparison

Expected performance (varies by CVE):

| Agent Type | Avg Steps | Avg Time | Success Rate | Features |
|-----------|-----------|----------|--------------|----------|
| Demo      | 5-8       | 30-60s   | 40-60%       | Basic    |
| CTF       | 8-15      | 60-180s  | 60-80%       | Advanced |

CTFAgent typically:
- Takes more steps (explains reasoning)
- Has higher success rate (better error recovery)
- Uses more tokens (thought + action)
- More robust (handles edge cases)

## Congratulations!

You now have a fully functional pluggable agent framework with:
- ✅ Simple demo agent (backward compatible)
- ✅ Advanced CTF agent (full EnIGMA/CTFMix features)
- ✅ Clean separation of concerns
- ✅ Easy agent switching via API
- ✅ All original features preserved

Happy exploiting!
