# Worker Unit Agent Tests

Simple tests for Demo and CTF agents.

## Files

```
test/worker_unit/
├── test_rollout.py        # Python test for Demo agent
├── test_rollout.sh        # Bash wrapper for Demo agent
├── test_ctf_agent.py      # Python test for CTF agent
└── test_ctf_agent.sh      # Bash wrapper for CTF agent
```

## Quick Start

### 1. Install Dependencies (One-time)

```bash
cd worker_orchestrator
bash setup.sh
```

### 2. Start LLM Server (Terminal 1)

```bash
cd worker_orchestrator
bash start_llm_server.sh
# Wait for "Uvicorn running on http://0.0.0.0:8001"
# Leave running
```

### 3. Test Demo Agent (Terminal 2)

**In WSL:**
```bash
cd worker_orchestrator
bash test/worker_unit/test_rollout.sh
```

**Or in PowerShell:**
```powershell
cd E:\git_fork_folder\VulRL\worker_orchestrator
.\venv\Scripts\Activate.ps1
python test/worker_unit/test_rollout.py
```

### 4. Test CTF Agent (Terminal 2)

**In WSL:**
```bash
cd worker_orchestrator
bash test/worker_unit/test_ctf_agent.sh
```

**Or in PowerShell:**
```powershell
cd E:\git_fork_folder\VulRL\worker_orchestrator
.\venv\Scripts\Activate.ps1
python test/worker_unit/test_ctf_agent.py
```

## Expected Behavior

### Demo Agent
- Simple, direct bash commands
- No explanations
- Fast execution (~1-2 min)
- Output shows: Action → Observation → Reward

### CTF Agent
- Explains reasoning (Thought)
- Formatted actions in code blocks
- Slower execution (~2-5 min)
- Output shows: Thought → Action → Observation → Reward

## Troubleshooting

### Error: Docker SDK proxy issues in WSL

```bash
# Unset proxies before running:
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
bash test/worker_unit/test_rollout.sh
```

### Error: LLM server not running

```bash
# Check server status:
curl http://127.0.0.1:8001/health

# If not running, start it:
bash start_llm_server.sh
```

### Error: ModuleNotFoundError

```bash
# Install dependencies:
bash setup.sh
```

## Comparing Agents

To compare both agents, run them sequentially:

```bash
# Demo agent
bash test/worker_unit/test_rollout.sh > demo_result.txt

# CTF agent  
bash test/worker_unit/test_ctf_agent.sh > ctf_result.txt

# Compare
diff demo_result.txt ctf_result.txt
```

Look for differences in:
- Number of steps taken
- Quality of reasoning (CTF shows thoughts)
- Success rates
- Execution times

## Next Steps

1. Run both tests to verify they work
2. Try with different CVEs
3. Adjust max_steps, temperature as needed
4. Monitor which agent works better for which CVE types
5. Integrate into your workflow
