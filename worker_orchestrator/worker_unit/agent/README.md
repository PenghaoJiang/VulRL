# VulRL Agent Framework

Pluggable agent architecture for security testing tasks.

## Architecture

```
worker_unit/agent/
├── base_agent.py           # Abstract base class for all agents
├── demo_agent/             # Simple bash command agent
│   └── demo_agent.py       # Original agent_loop logic
├── ctf_agent/              # Advanced CTFMix agent
│   ├── ctf_agent.py        # Main CTF agent wrapper
│   ├── llm_adapter.py      # Adapts InferenceEngineClientWrapper to CTFMix model interface
│   ├── runtime_adapter.py  # Adapts VulhubAdapter to CTFMixRuntime interface
│   ├── type_converters.py  # Converts between CTFMix and worker_router types
│   └── ctfmix/             # Full CTFMix/EnIGMA codebase
│       ├── agents.py       # Core Agent class with thought/action parsing
│       ├── runtime.py      # CTFMixRuntime (reference, not used directly)
│       ├── models.py       # LLM providers (OpenAI only)
│       ├── parsing.py      # Thought/action parsers
│       ├── commands.py     # Command parsing
│       └── ...             # Other CTFMix modules
└── config/                 # Agent configuration files
    ├── default_ctf.yaml    # Default CTF agent config
    ├── models_config.yaml  # Model metadata (context, costs)
    └── commands/           # Bash command definitions
```

## Agent Types

### DemoAgent (Simple)
- **Purpose**: Basic bash command execution
- **Input**: Plain text prompt
- **Output**: Raw bash commands
- **Features**: None (minimal viable agent)
- **Use case**: Quick testing, baseline comparisons

### CTFAgent (Advanced)
- **Purpose**: Sophisticated CTF-style exploitation
- **Input**: Structured prompts with task descriptions
- **Output**: Thought + action (explains reasoning before acting)
- **Features**:
  - Thought/action parsing (model explains before acting)
  - Interactive sessions (vim, radare2, python REPL)
  - History summarization (for long episodes)
  - Multi-line commands with heredoc
  - Command blocklists (prevents dangerous commands)
  - Format error recovery (retries malformed outputs)
  - Submission detection (<<SUBMISSION||flag||SUBMISSION>>)
- **Use case**: Production exploitation, research experiments

## Usage

### From RolloutExecutor

```python
from worker_unit.rollout_executor import RolloutExecutor

executor = RolloutExecutor()

# Use demo agent (default)
result = await executor.execute(request, agent_type="demo")

# Use CTF agent
result = await executor.execute(request, agent_type="ctf")
```

### From Worker Router

```python
# Add agent_type to RolloutRequest metadata
request = RolloutRequest(
    cve_id="CVE-2023-1234",
    vulhub_path="some/path",
    prompt="Exploit this vulnerability",
    llm_endpoint="http://localhost:8000/generate",
    model_name="gpt-4",
    metadata={"agent_type": "ctf"}  # or "demo"
)
```

## Integration Points

### 1. LLM Integration
- CTFAgent uses `llm_adapter.py` to bridge `InferenceEngineClientWrapper` → CTFMix model interface
- Async calls are handled transparently
- Model stats (tokens, costs) tracked automatically

### 2. Environment Integration
- CTFAgent uses `runtime_adapter.py` to bridge `VulhubAdapter` → `CTFMixRuntime` interface
- Container management stays in VulhubAdapter
- Command execution uses shared `DockerExecutor`

### 3. Type System Integration
- `type_converters.py` converts between:
  - CTFMix `TrajectoryStep` (thought, response, state) 
  - worker_router `TrajectoryStep` (step, action, observation, reward, done)

## Configuration

### Agent Config Files

Stored in `agent/config/`:
- `default_ctf.yaml`: Agent templates, commands, parsing settings
- `models_config.yaml`: Model metadata (context windows, costs)
- `commands/*.sh`: Bash functions available to agent

### Environment Variables

CTFMix uses environment variables for API keys (stored in `.env` or system env):
- `OPENAI_API_KEY`: OpenAI API key (if using OpenAI models)
- `OPENAI_API_BASE_URL`: Custom OpenAI endpoint (optional)

For VulRL, these are not needed since we use `InferenceEngineClientWrapper`.

## Dependencies

Added to `requirements.txt`:
- `simple-parsing==0.1.5`: Config serialization
- `tenacity==8.2.3`: Retry logic
- `openai==1.12.0`: OpenAI API client

## Implementation Notes

### Design Decision: Option B (RolloutExecutor owns agent)
- Agent created fresh for each execution request
- Clean separation: Environment = Docker, Agent = reasoning
- Easy to test agents independently
- Clear lifecycle management

### Docker Execution
- Extracted to `docker/docker_executor.py` for reusability
- Supports both Docker SDK (preferred) and subprocess (fallback)
- Used by both VulhubAdapter and agents

### CTFMix Modifications
- Removed non-OpenAI providers (Anthropic, Groq, Together, Bedrock, Ollama)
- Modified `config.py` to find configs in worker_unit structure
- All other CTFMix code kept intact for full feature support

## Future Enhancements

1. **Agent pooling**: Reuse agents across requests for efficiency
2. **Custom parsers**: Add VulRL-specific action parsers
3. **Multi-agent**: Support agent ensembles or specialized sub-agents
4. **Streaming**: Stream agent thoughts and actions in real-time
5. **Checkpointing**: Save/resume agent state mid-execution

## Testing

Test files in `test/worker_unit/`:
- Test agent creation and initialization
- Test trajectory conversion
- Test agent switching (demo vs ctf)
- Integration tests with real Vulhub environments

## Troubleshooting

### Import Errors
- Ensure `setup.sh` completed successfully
- Check that all dependencies are installed
- Verify config files exist in `agent/config/`

### CTFMix Agent Errors
- Check that `default_ctf.yaml` exists
- Verify container has necessary tools (curl, python, etc.)
- Check LLM endpoint is accessible

### Type Conversion Errors
- Verify trajectory format matches expectations
- Check that AgentInfo contains expected fields
- Validate observation/action string conversions
