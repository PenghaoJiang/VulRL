#!/bin/bash
# Install vLLM separately (large package, may need proxy settings)

set -e

echo "Installing vLLM..."
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

# Check for proxy issues
if [ ! -z "$http_proxy" ] || [ ! -z "$https_proxy" ]; then
    echo "⚠️  Proxy detected: $http_proxy $https_proxy"
    echo ""
    echo "If installation fails, try:"
    echo "  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY"
    echo "  bash install_vllm.sh"
    echo ""
    read -p "Continue with current proxy settings? (y/N): " -n 1 -r
    echo ""
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Installation cancelled"
        echo ""
        echo "To disable proxy and try again:"
        echo "  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY"
        echo "  bash install_vllm.sh"
        exit 1
    fi
fi

# Install vLLM
echo "Installing vLLM (this may take 5-10 minutes)..."
echo ""

pip install -r requirements-llm.txt --no-cache-dir

if [ $? -eq 0 ]; then
    echo ""
    echo "========================================="
    echo "✓ vLLM installed successfully!"
    echo "========================================="
    echo ""
    echo "You can now start the LLM server:"
    echo "  bash start_llm_server.sh"
else
    echo ""
    echo "✗ vLLM installation failed!"
    echo ""
    echo "Common issues:"
    echo "1. Proxy problems - disable with: unset http_proxy https_proxy"
    echo "2. CUDA version mismatch - check CUDA version with: nvidia-smi"
    echo "3. Network issues - try again later"
    echo ""
    echo "For manual installation:"
    echo "  source venv/bin/activate"
    echo "  pip install vllm --no-cache-dir"
    exit 1
fi
