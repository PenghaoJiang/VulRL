# vLLM Server

⚠️ **Note**: This server is now managed from the `worker_orchestrator` root directory.

## 📝 Quick Start

All startup scripts have been moved to `worker_orchestrator/` root:

```bash
cd /mnt/e/git_fork_folder/VulRL/worker_orchestrator

# Start LLM server
bash start_llm_server.sh

# Stop LLM server
bash stop_llm_server.sh

# Or start all services
bash start_all.sh
```

## 📖 Documentation

See main documentation:
- `../../README.md` - Main project README
- `../../STARTUP_GUIDE.md` - Complete startup guide
- `../README.md` - EZ LLM Server overview

## 🔧 Configuration

Edit `../../start_llm_server.sh` to change:
- Model path
- Server host/port
- GPU memory usage

Current configuration:
- Model: `/mnt/e/models/qwen2.5-1.5b`
- Served as: `qwen2.5-1.5b`
- Host: `127.0.0.1`
- Port: `8001`
