#!/bin/bash
# Start vLLM server with local Qwen model

set -e

echo "Starting vLLM server with local Qwen 2.5 1.5B model..."
echo ""

# Get script directory and activate venv
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "✗ Virtual environment not found!"
    echo ""
    echo "Please run setup first:"
    echo "  bash setup.sh"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check if vllm is installed
if ! python -c "import vllm" 2>/dev/null; then
    echo "✗ vLLM not installed in venv!"
    echo ""
    echo "Please run setup to install dependencies:"
    echo "  bash setup.sh"
    exit 1
fi

# Model path (local model)
MODEL_PATH="/mnt/e/models/qwen2.5-1.5b"

# Check if model exists
if [ ! -d "$MODEL_PATH" ]; then
    echo "✗ Model not found at: $MODEL_PATH"
    echo ""
    echo "Please ensure the model exists at this location"
    exit 1
fi

# Server settings
# Use 0.0.0.0 for WSL2 compatibility (accessible from Windows and other WSL terminals)
HOST="0.0.0.0"
PORT=8001

# Model name for API (used in client requests)
# This is what clients will use in their "model" field
SERVED_MODEL_NAME="qwen2.5-1.5b"

echo "Model path: $MODEL_PATH"
echo "Served as: $SERVED_MODEL_NAME"
echo "Server: http://${HOST}:${PORT} (listening on all interfaces)"
echo "Access at: http://127.0.0.1:${PORT}"
echo "API docs: http://127.0.0.1:${PORT}/docs"
echo ""
echo "Press Ctrl+C to stop"
echo ""

# Disable V1 multiprocessing (same as SkyRL for WSL2 compatibility)
# See: skyrl_train/inference_engines/vllm/vllm_engine.py:81
export VLLM_ENABLE_V1_MULTIPROCESSING=0

# Start vLLM with OpenAI-compatible API
# Matches SkyRL config from run_training.sh:
# - max_model_len: 2048 (same as SkyRL)
# - enable_chunked_prefill: False (same as SkyRL)  
# - gpu_memory_utilization: 0.65 (standalone needs more than SkyRL's 0.40)
# - distributed-executor-backend: ray (avoid V1 mp engine WSL2 IPC issues)
python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_PATH" \
    --served-model-name "$SERVED_MODEL_NAME" \
    --host "$HOST" \
    --port "$PORT" \
    --max-model-len 2048 \
    --gpu-memory-utilization 0.65 \
    --no-enable-chunked-prefill \
    --disable-log-stats \
    --distributed-executor-backend ray 
