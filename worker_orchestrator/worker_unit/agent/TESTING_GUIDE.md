# Agent Framework Testing Guide

## Pre-Testing Setup

### 1. Install Dependencies

```bash
cd worker_orchestrator
bash setup.sh
```

Expected output:
```
✓ fastapi already installed
✓ uvicorn already installed
...
Installing missing packages: simple-parsing tenacity
...
✓ Setup complete!
```

### 2. Verify Installation

```bash
python3 << 'EOF'
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

# Test core imports
from worker_unit.agent import BaseAgent
from worker_unit.agent.demo_agent import DemoAgent
from worker_unit.agent.ctf_agent import CTFAgent
from worker_unit.adapters.docker_executor import DockerExecutor

print("✓ All core imports successful")

# Test CTFMix imports
from worker_unit.agent.ctf_agent.ctfmix.agents import Agent
from worker_unit.agent.ctf_agent.ctfmix.models import OpenAIModel
from worker_unit.agent.ctf_agent.ctfmix.parsing import ThoughtActionParser

print("✓ CTFMix imports successful")

# Test adapters
from worker_unit.agent.ctf_agent.llm_adapter import LLMAdapter
from worker_unit.agent.ctf_agent.runtime_adapter import VulhubRuntimeAdapter
from worker_unit.agent.ctf_agent.type_converters import ctfmix_trajectory_to_worker

print("✓ Adapter imports successful")

print("\n✅ All imports verified - ready for testing!")
EOF
```

### 3. Verify Config Files

```bash
# Check all config files exist
ls -R worker_unit/agent/config/

# Verify key files
test -f worker_unit/agent/config/default_ctf.yaml && echo "✓ default_ctf.yaml found"
test -f worker_unit/agent/config/models_config.yaml && echo "✓ models_config.yaml found"
test -d worker_unit/agent/config/commands && echo "✓ commands directory found"
```

## Testing Plan

### Phase 1: Unit Tests (No Docker Required)

#### Test 1: Base Agent Interface

```python
from worker_unit.agent import BaseAgent

# Verify abstract class can't be instantiated
try:
    agent = BaseAgent(None, None)
    print("❌ BaseAgent should not be instantiable")
except TypeError:
    print("✓ BaseAgent is properly abstract")
```

#### Test 2: DemoAgent Creation

```python
from worker_unit.agent.demo_agent import DemoAgent

# Create with mock dependencies
class MockEnv:
    async def step(self, action):
        return "mock observation", 0.0, False, False, {"test": True}

class MockLLM:
    async def generate(self, input):
        return {"responses": ["echo 'test'"]}

agent = DemoAgent(
    env=MockEnv(),
    llm_client=MockLLM(),
    config={}
)

print(f"✓ DemoAgent created: {agent.get_name()}")
```

#### Test 3: Type Converters

```python
from worker_unit.agent.ctf_agent.type_converters import ctfmix_trajectory_to_worker

# Test conversion
ctf_traj = [
    {
        "action": "curl http://target",
        "observation": "200 OK",
        "thought": "Let me check the target",
        "response": "I will curl the target",
        "state": "{}",
        "execution_time": 1.5
    }
]

agent_info = {
    "exit_status": "submitted",
    "submission": "flag{test}",
    "score": 1.0
}

worker_traj = ctfmix_trajectory_to_worker(ctf_traj, agent_info)
assert len(worker_traj) == 1
assert worker_traj[0].action == "curl http://target"
assert worker_traj[0].metadata["thought"] == "Let me check the target"

print("✓ Type conversion works correctly")
```

### Phase 2: Integration Tests (Docker Required)

#### Test 4: DemoAgent with Real Environment

```bash
# Create test script
cat > test_demo_agent.py << 'EOF'
import asyncio
import sys
sys.path.insert(0, '.')

from worker_router.models import RolloutRequest
from worker_unit.rollout_executor import RolloutExecutor

async def test_demo():
    request = RolloutRequest(
        cve_id="TEST-DEMO",
        vulhub_path="activemq/CVE-2023-46604",
        prompt="Check if the ActiveMQ service is running at http://target:8161",
        llm_endpoint="http://localhost:8000/generate",
        model_name="gpt-4",
        max_steps=3,
        temperature=0.7,
        max_tokens=256,
        metadata={"agent_type": "demo"}
    )
    
    executor = RolloutExecutor()
    result = await executor.execute(request, agent_type="demo")
    
    print(f"Status: {result.status}")
    print(f"Steps: {len(result.trajectory) if result.trajectory else 0}")
    print(f"Reward: {result.reward}")
    print(f"Success: {result.success}")
    
    if result.trajectory:
        print("\nFirst 3 steps:")
        for step in result.trajectory[:3]:
            print(f"  Step {step.step}: {step.action[:50]}...")

asyncio.run(test_demo())
EOF

# Run test
python3 test_demo_agent.py
```

Expected output:
```
[RolloutExecutor] Creating agent (type: demo)...
[DemoAgent] Step 1/3
[DemoAgent] Action: curl http://target:8161
...
Status: completed
Steps: 3
Reward: <depends on CVE>
```

#### Test 5: CTFAgent with Real Environment

```bash
# Create test script
cat > test_ctf_agent.py << 'EOF'
import asyncio
import sys
sys.path.insert(0, '.')

from worker_router.models import RolloutRequest
from worker_unit.rollout_executor import RolloutExecutor

async def test_ctf():
    request = RolloutRequest(
        cve_id="TEST-CTF",
        vulhub_path="activemq/CVE-2023-46604",
        prompt="Exploit the ActiveMQ RCE vulnerability to gain remote code execution",
        llm_endpoint="http://localhost:8000/generate",
        model_name="gpt-4",
        max_steps=10,
        temperature=0.7,
        max_tokens=1024,
        metadata={"agent_type": "ctf"}
    )
    
    executor = RolloutExecutor()
    result = await executor.execute(request, agent_type="ctf")
    
    print(f"Status: {result.status}")
    print(f"Steps: {len(result.trajectory) if result.trajectory else 0}")
    print(f"Reward: {result.reward}")
    print(f"Success: {result.success}")
    
    if result.trajectory:
        print("\nFirst 3 steps:")
        for step in result.trajectory[:3]:
            print(f"\nStep {step.step}:")
            print(f"  Thought: {step.metadata.get('thought', 'N/A')[:80]}...")
            print(f"  Action: {step.action[:80]}...")
            print(f"  Observation: {step.observation[:80]}...")

asyncio.run(test_ctf())
EOF

# Run test
python3 test_ctf_agent.py
```

Expected output:
```
[RolloutExecutor] Creating agent (type: ctf)...
[CTFAgent] Starting CTFMix agent run
[CTF Agent Thought]: I need to identify the ActiveMQ version...
[CTF Agent Action]: curl -i http://target:8161
...
Status: completed
Steps: 10
Success: true
```

### Phase 3: Comparison Tests

#### Test 6: Side-by-Side Comparison

```python
import asyncio
from worker_router.models import RolloutRequest
from worker_unit.rollout_executor import RolloutExecutor

async def compare_agents():
    # Same CVE, same prompt, different agents
    cve = "activemq/CVE-2023-46604"
    prompt = "Exploit the ActiveMQ RCE vulnerability"
    
    executor = RolloutExecutor()
    
    # Test demo agent
    demo_request = RolloutRequest(
        cve_id=f"{cve}-demo",
        vulhub_path=cve,
        prompt=prompt,
        llm_endpoint="http://localhost:8000/generate",
        model_name="gpt-4",
        max_steps=15,
        metadata={"agent_type": "demo"}
    )
    demo_result = await executor.execute(demo_request, agent_type="demo")
    
    # Test CTF agent
    ctf_request = RolloutRequest(
        cve_id=f"{cve}-ctf",
        vulhub_path=cve,
        prompt=prompt,
        llm_endpoint="http://localhost:8000/generate",
        model_name="gpt-4",
        max_steps=15,
        metadata={"agent_type": "ctf"}
    )
    ctf_result = await executor.execute(ctf_request, agent_type="ctf")
    
    # Compare results
    print("="*70)
    print("COMPARISON RESULTS")
    print("="*70)
    print(f"\nDemo Agent:")
    print(f"  Steps: {len(demo_result.trajectory)}")
    print(f"  Reward: {demo_result.reward}")
    print(f"  Success: {demo_result.success}")
    print(f"  Duration: {demo_result.duration:.1f}s")
    
    print(f"\nCTF Agent:")
    print(f"  Steps: {len(ctf_result.trajectory)}")
    print(f"  Reward: {ctf_result.reward}")
    print(f"  Success: {ctf_result.success}")
    print(f"  Duration: {ctf_result.duration:.1f}s")
    
    print(f"\nWinner: {'CTF' if ctf_result.reward > demo_result.reward else 'Demo'}")

asyncio.run(compare_agents())
```

## Troubleshooting

### Error: ModuleNotFoundError: No module named 'simple_parsing'

```bash
# Fix: Install dependencies
bash setup.sh

# Or manually
pip install simple-parsing tenacity openai
```

### Error: ModuleNotFoundError: No module named 'worker_unit'

```bash
# Fix: Add to PYTHONPATH
cd worker_orchestrator
export PYTHONPATH=$(pwd):$PYTHONPATH
python3 your_test.py
```

### Error: FileNotFoundError: Agent config not found

```bash
# Check config files
ls worker_unit/agent/config/

# If missing, copy manually
cp -r /path/to/git_folk_folder_02/VulRL/benchmark/ctfmix/config/* \
      worker_unit/agent/config/
```

### Error: ImportError: attempted relative import with no known parent package

```bash
# Fix: Run from worker_orchestrator root
cd worker_orchestrator
python3 -m worker_unit.main --worker-id test
```

### Error: docker.errors.APIError: 500 Server Error

```bash
# Fix: Check Docker daemon
docker ps

# If not running, start Docker
sudo systemctl start docker  # Linux
# or restart Docker Desktop (Windows/Mac)
```

### Error: RuntimeError: Container not initialized

```bash
# This means VulhubAdapter.setup() failed
# Check:
1. Docker daemon is running
2. Vulhub path exists
3. Docker compose files are valid
4. No port conflicts
```

### Error: AttributeError: 'VulhubAdapter' object has no attribute 'attacker_container_obj'

```bash
# This means you're using an old version of VulhubAdapter
# Fix: Ensure you're using the modified version (should have Docker SDK imports)
grep "docker.models.containers" worker_unit/adapters/vulhub_adapter.py
```

## Success Criteria

### DemoAgent
- ✅ Imports successfully
- ✅ Creates without errors
- ✅ Executes bash commands
- ✅ Returns trajectory
- ✅ Produces same results as old agent_loop

### CTFAgent
- ✅ Imports successfully
- ✅ Creates without errors
- ✅ Parses thought/action from LLM
- ✅ Executes commands via runtime adapter
- ✅ Returns trajectory with thoughts
- ✅ Handles interactive sessions (if needed)
- ✅ Detects submissions
- ✅ Higher success rate than DemoAgent

## Regression Testing

To ensure backward compatibility:

1. **Run existing CVE tests**: Verify demo agent produces same results as before
2. **Check trajectory format**: Ensure downstream systems (reward calculator) still work
3. **Verify API compatibility**: Existing clients should work without changes
4. **Test error handling**: Ensure graceful degradation on failures

## Performance Benchmarks

Recommended metrics to track:

| Metric | Demo Agent | CTF Agent | Notes |
|--------|-----------|-----------|-------|
| Avg Steps | ? | ? | Should be higher for CTF |
| Avg Time | ? | ? | Should be higher for CTF |
| Success Rate | ? | ? | Should be higher for CTF |
| Token Usage | ? | ? | Should be higher for CTF |
| Error Rate | ? | ? | Should be lower for CTF |

## Test CVEs

Recommended CVEs for initial testing (ordered by complexity):

### Easy
1. **CVE-2022-26134** (Confluence OGNL injection)
   - Simple RCE, one-step exploit
   - Good for basic functionality test

### Medium
2. **CVE-2023-46604** (ActiveMQ RCE)
   - Multi-step: discovery, payload crafting, execution
   - Tests parsing, command chaining

### Hard
3. **CVE-2021-41773** (Apache Path Traversal)
   - Requires exploration, file reading, payload crafting
   - Tests interactive sessions, summarization

## Debugging Tips

### Enable Debug Logging

```python
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(name)s] %(levelname)s: %(message)s'
)
```

### Inspect Agent State

```python
# In DemoAgent.run(), add after each step:
print(f"Messages so far: {len(messages)}")
print(f"Last message: {messages[-1]}")
```

### Inspect CTFMix State

```python
# In CTFAgent.run(), add:
print(f"CTFMix agent state: {self.ctfmix_agent.__dict__.keys()}")
print(f"Runtime state: {self.runtime_adapter.__dict__}")
```

### Check Container State

```bash
# While agent is running, in another terminal:
docker ps
docker exec -it attacker_vulhub_<id> bash
# Inside container:
ls -la /root/commands/
cat /root/commands/*.sh
env | grep LAST_ACTION
```

### Compare Trajectories

```python
def compare_trajectories(demo_traj, ctf_traj):
    print(f"Demo steps: {len(demo_traj)}")
    print(f"CTF steps: {len(ctf_traj)}")
    
    for i, (d, c) in enumerate(zip(demo_traj, ctf_traj)):
        print(f"\nStep {i}:")
        print(f"  Demo action: {d.action[:50]}...")
        print(f"  CTF action: {c.action[:50]}...")
        print(f"  CTF thought: {c.metadata.get('thought', 'N/A')[:50]}...")
```

## Stress Testing

### Test 1: Multiple Rollouts in Sequence

```python
async def stress_test():
    executor = RolloutExecutor()
    
    for i in range(10):
        request = RolloutRequest(
            cve_id=f"TEST-{i}",
            vulhub_path="activemq/CVE-2023-46604",
            prompt="Quick test",
            llm_endpoint="http://localhost:8000/generate",
            model_name="gpt-4",
            max_steps=3,
            metadata={"agent_type": "demo"}
        )
        
        result = await executor.execute(request, agent_type="demo")
        print(f"Run {i}: {result.status}")
    
    print("✓ 10 sequential rollouts completed")
```

### Test 2: Agent Switching

```python
async def test_agent_switching():
    executor = RolloutExecutor()
    
    for agent_type in ["demo", "ctf", "demo", "ctf"]:
        request = RolloutRequest(
            cve_id=f"TEST-{agent_type}",
            vulhub_path="activemq/CVE-2023-46604",
            prompt="Test",
            llm_endpoint="http://localhost:8000/generate",
            model_name="gpt-4",
            max_steps=3,
            metadata={"agent_type": agent_type}
        )
        
        result = await executor.execute(request, agent_type=agent_type)
        print(f"{agent_type.upper()}: {result.status}")
    
    print("✓ Agent switching works")
```

### Test 3: Error Recovery

```python
async def test_error_recovery():
    executor = RolloutExecutor()
    
    # Test with invalid CVE path
    request = RolloutRequest(
        cve_id="TEST-INVALID",
        vulhub_path="nonexistent/path",
        prompt="Test",
        llm_endpoint="http://localhost:8000/generate",
        model_name="gpt-4",
        max_steps=3,
        metadata={"agent_type": "demo"}
    )
    
    result = await executor.execute(request, agent_type="demo")
    assert result.status == "failed"
    assert result.error is not None
    print("✓ Error handling works")
```

## Validation Checklist

Before deploying to production:

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Both agents work with at least 3 different CVEs
- [ ] Trajectory format is correct
- [ ] Reward calculation still works
- [ ] Error handling is graceful
- [ ] Performance is acceptable (< 3 minutes per CVE)
- [ ] Memory usage is reasonable (< 2GB per rollout)
- [ ] No container leaks (all cleaned up)
- [ ] No zombie processes
- [ ] Logs are informative
- [ ] Documentation is complete

## Rollback Plan

If critical issues are found:

### Option 1: Disable CTF Agent

```python
# In rollout_executor.py, force demo agent:
if agent_type == "ctf":
    print("WARNING: CTF agent temporarily disabled, using demo")
    agent_type = "demo"
```

### Option 2: Revert to Original agent_loop

```python
# In rollout_executor.py, uncomment old code:
trajectory = await agent_loop(
    env=env,
    llm_client=llm_client,
    initial_prompt=request.prompt,
    observation=observation,
    max_steps=request.max_steps,
    temperature=request.temperature,
    max_tokens=request.max_tokens
)
```

### Option 3: Full Rollback

```bash
# Revert all changes (assuming they're committed)
git revert <commit-hash>
```

## Success Metrics

Track these metrics to measure improvement:

1. **Success Rate**: % of CVEs successfully exploited
2. **Average Steps**: Number of steps to completion
3. **Average Time**: Execution time per CVE
4. **Token Efficiency**: Tokens used per successful exploit
5. **Error Rate**: % of rollouts that crash or fail
6. **Submission Accuracy**: % of correct flags (if available)

## Expected Results

Based on EnIGMA/CTFMix papers:

- **DemoAgent**: ~40-60% success on simple CVEs
- **CTFAgent**: ~60-80% success on simple CVEs, ~40-60% on complex
- **Thought Quality**: CTFAgent should explain reasoning clearly
- **Error Recovery**: CTFAgent should retry on format errors
- **Interactive Sessions**: CTFAgent should handle vim, python REPL

## Continuous Monitoring

Once deployed, monitor:

1. Agent selection distribution (demo vs ctf usage)
2. Success rates per agent type
3. Common failure modes
4. Token usage and costs
5. Execution times
6. Container resource usage

## Questions to Answer

After testing, document:

1. Which agent works better for which CVE types?
2. What's the optimal max_steps for each agent?
3. What's the optimal temperature for exploitation tasks?
4. Are there CVEs where demo agent is sufficient?
5. What features of CTFAgent are most valuable?
6. What's the cost increase of using CTF vs Demo?

## Ready to Test!

Your implementation is complete and ready for testing. Start with Phase 1 unit tests, then move to Phase 2 integration tests.

Good luck!
