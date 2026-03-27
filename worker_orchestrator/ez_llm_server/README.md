# EZ LLM Server

Simple vLLM-based inference server with Python client that mimics SkyRL's `InferenceEngineClient` interface.

## 📁 Structure

```
ez_llm_server/
├── server/                          # vLLM HTTP server
│   ├── config.yaml                  # Server configuration
│   ├── start_vllm.sh                # Start production server (Qwen)
│   ├── start_small.sh               # Start test server (TinyLlama)
│   └── README.md                    # Server docs
│
├── client/                          # Python client (mimics SkyRL)
│   ├── __init__.py
│   ├── inference_client_wrapper.py  # Main client class
│   └── README.md                    # Client docs
│
├── test/
│   ├── test_generate.py             # Test Python client
│   └── test_simple.sh               # Test HTTP endpoints
│
└── README.md                        # This file
```

## 🎯 Purpose

This provides:
1. **vLLM HTTP Server**: OpenAI-compatible API for LLM inference
2. **Python Client Wrapper**: Mimics SkyRL's `InferenceEngineClient` interface
3. **Worker Integration**: Workers use the Python client directly

## 🚀 Quick Start

### Prerequisites

The model should be at:
```
/mnt/e/models/qwen2.5-1.5b  (WSL)
E:\models\qwen2.5-1.5b       (Windows)
```

### Setup (from worker_orchestrator root)

```bash
cd /mnt/e/git_fork_folder/VulRL/worker_orchestrator

# 1. Setup venv and install all dependencies (including vLLM)
bash setup.sh

# 2. Start LLM server
bash start_llm_server.sh
```

### Test

```bash
# Test HTTP endpoints
cd ez_llm_server/test
bash test_local_simple.sh

# Test Python client
python test_local_model.py
```

## 📝 Note

The LLM server now uses the **shared venv** from `worker_orchestrator/venv/`.
All dependencies (FastAPI, vLLM, etc.) are installed via the main `setup.sh`.

Expected output:
```
Testing Local Qwen 2.5 1.5B Model
============================================================

✓ Client initialized
  Endpoint: http://127.0.0.1:8001
  Model: qwen2.5-1.5b

Input:
  Prompt: Write a Python script in bash format to print 'Hello World'
  Max tokens: 200
  Temperature: 0.7

Generating response...

============================================================
Response:
============================================================
#!/bin/bash
python3 << EOF
print('Hello World')
EOF

============================================================
Stop reason: stop
============================================================
✓ Test completed successfully!
```

## 📖 Usage

### In Worker Unit

```python
from ez_llm_server.client import InferenceEngineClientWrapper

# Initialize (same interface as SkyRL!)
# Use the served-model-name from start_vllm.sh
client = InferenceEngineClientWrapper(
    endpoint="http://127.0.0.1:8001",
    model_name="qwen2.5-1.5b"  # Local model name
)

# Generate (same interface as SkyRL!)
engine_input = {
    "prompts": [[
        {"role": "user", "content": "Hello!"}
    ]],
    "sampling_params": {
        "max_tokens": 100,
        "temperature": 0.7,
    }
}

engine_output = await client.generate(engine_input)
response = engine_output["responses"][0]
```

### Batch Generation

```python
# Multiple prompts in a batch
engine_input = {
    "prompts": [
        [{"role": "user", "content": "Prompt 1"}],
        [{"role": "user", "content": "Prompt 2"}],
    ],
    "sampling_params": {
        "max_tokens": 100,
        "temperature": 0.7,
    }
}

engine_output = await client.generate(engine_input)
responses = engine_output["responses"]  # List of 2 responses
```

## 🔄 Architecture

```
┌─────────────────────────────────────┐
│  Worker Unit (Python)               │
│  - Uses InferenceEngineClientWrapper│
│  - Same interface as SkyRL          │
└──────────────┬──────────────────────┘
               │ (Python method call)
               ▼
┌─────────────────────────────────────┐
│  InferenceEngineClientWrapper       │
│  - Mimics SkyRL's interface         │
│  - Converts to HTTP internally      │
└──────────────┬──────────────────────┘
               │ (HTTP POST /v1/chat/completions)
               ▼
┌─────────────────────────────────────┐
│  vLLM HTTP Server                   │
│  - OpenAI-compatible API            │
│  - Actual LLM inference             │
└─────────────────────────────────────┘
```

## 📊 API Interface

### Input Format (Same as SkyRL)

```python
InferenceEngineInput = {
    "prompts": List[List[Dict[str, str]]],  # Batch of conversations
    "sampling_params": {
        "max_tokens": int,
        "temperature": float,
        "top_p": float,
        "stop": Optional[List[str]],
    }
}
```

### Output Format (Same as SkyRL)

```python
InferenceEngineOutput = {
    "responses": List[str],          # Generated responses
    "stop_reasons": List[str],       # "stop", "length", etc.
    "response_ids": List[List[int]], # Token IDs (empty for now)
}
```

## 🧪 Testing

### Test HTTP Endpoints

```bash
cd test
bash test_simple.sh
```

### Test Python Client

```bash
cd test
python test_generate.py
```

## 🔧 Configuration

Edit `server/config.yaml`:

```yaml
model:
  name: "Qwen/Qwen2.5-7B-Instruct"  # Change model
  max_model_len: 4096
  gpu_memory_utilization: 0.9

server:
  host: "127.0.0.1"
  port: 8001
```

## 🐛 Troubleshooting

### Server not starting

```bash
# Check if port 8001 is already in use
lsof -i :8001

# Kill existing process
kill -9 <PID>
```

### Client connection error

```bash
# Make sure server is running
curl http://127.0.0.1:8001/health

# Should return: {"status":"ok"}
```

### CUDA out of memory

```bash
# Use smaller model
cd server
bash start_small.sh

# Or reduce GPU memory usage in start_vllm.sh
# Change: --gpu-memory-utilization 0.9
# To: --gpu-memory-utilization 0.7
```

## 📚 Documentation

- **Server**: See `server/README.md`
- **Client**: See `client/inference_client_wrapper.py` docstrings
- **vLLM docs**: https://docs.vllm.ai/

---

**Status**: Ready for testing ✅
