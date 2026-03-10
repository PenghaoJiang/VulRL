# Quick Start Guide - Local Qwen 2.5 1.5B

This guide walks you through starting the vLLM server with your local Qwen 2.5 1.5B model.

## ✅ Prerequisites

1. **Model Location**: `/mnt/e/models/qwen2.5-1.5b` (WSL) or `E:\models\qwen2.5-1.5b` (Windows)
2. **vLLM installed**: `pip install vllm`
3. **GPU available**: Check with `nvidia-smi`

## 🚀 Step-by-Step

### 1. Navigate to Worker Orchestrator Root

```bash
cd /mnt/e/git_fork_folder/VulRL/worker_orchestrator
```

### 2. Ensure Setup is Done

```bash
# If not done yet, run setup to create venv and install deps
bash setup.sh
```

### 3. Start vLLM Server

```bash
bash start_llm_server.sh
```

**Expected output**:
```
Starting vLLM server with local Qwen 2.5 1.5B model...

✓ Model path: /mnt/e/models/qwen2.5-1.5b
✓ Served as: qwen2.5-1.5b
✓ Server: http://127.0.0.1:8001
✓ API docs: http://127.0.0.1:8001/docs

Press Ctrl+C to stop

INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://127.0.0.1:8001
```

### 3. Test Server (in another terminal)

```bash
# Quick health check
curl http://127.0.0.1:8001/health

# Should return: {"status":"ok"}
```

### 4. Test with Python Client

```bash
cd ../test
python test_local_model.py
```

**Expected output**:
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

## 🔧 Configuration

The server uses these settings (in `start_vllm.sh`):

| Setting | Value | Description |
|---------|-------|-------------|
| Model Path | `/mnt/e/models/qwen2.5-1.5b` | Local model directory |
| Served Name | `qwen2.5-1.5b` | API model name |
| Host | `127.0.0.1` | Server host |
| Port | `8001` | Server port |
| Max Length | `4096` | Max sequence length |
| GPU Memory | `0.9` | 90% GPU utilization |

## 📝 Using in Worker Unit

Update your worker configuration to use the local model:

```python
# In worker_unit/main.py or rollout request
llm_endpoint = "http://127.0.0.1:8001"
model_name = "qwen2.5-1.5b"  # Must match --served-model-name

client = InferenceEngineClientWrapper(
    endpoint=llm_endpoint,
    model_name=model_name
)
```

## 🐛 Troubleshooting

### Error: Model not found

```bash
✗ Model not found at: /mnt/e/models/qwen2.5-1.5b
```

**Solution**: Check model path
```bash
ls /mnt/e/models/qwen2.5-1.5b
# Should see: config.json, model files, tokenizer files, etc.
```

### Error: CUDA out of memory

**Solution 1**: Reduce GPU memory utilization
```bash
# Edit start_vllm.sh
# Change: --gpu-memory-utilization 0.9
# To: --gpu-memory-utilization 0.7
```

**Solution 2**: Close other GPU processes
```bash
nvidia-smi  # Check what's using GPU
kill -9 <PID>  # Kill other processes
```

### Error: Port 8001 already in use

**Solution**: Kill existing process
```bash
lsof -i :8001  # Find process using port
kill -9 <PID>  # Kill it
```

Or change port in `start_vllm.sh`:
```bash
PORT=8002  # Use different port
```

## 🎯 Next Steps

1. ✅ Server running
2. ✅ Test passed
3. 🔜 Use in Worker Router:
   ```bash
   cd /mnt/e/git_fork_folder/VulRL/worker_orchestrator/test/worker_router
   bash _api_rollout_execute.sh
   ```

---

**Need help?** Check `server/README.md` for more details.
