#!/bin/bash
# Setup virtual environment and install dependencies

set -e

echo "Setting up VulRL Worker Router..."
echo ""

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "✗ Python3 not found!"
    echo "Please install Python 3.10+ first"
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Check for proxy issues and unset if needed
if [ ! -z "$http_proxy" ] || [ ! -z "$https_proxy" ]; then
    echo "Detected proxy settings. If installation fails, try:"
    echo "  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY"
    echo "  bash setup.sh"
    echo ""
fi

# Upgrade pip (without proxy if it fails)
echo "Upgrading pip..."
pip install --upgrade pip --no-cache-dir || {
    echo "Failed with proxy, retrying without proxy..."
    unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY
    pip install --upgrade pip --no-cache-dir
}

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt --no-cache-dir || {
    echo ""
    echo "✗ Installation failed!"
    echo ""
    echo "If you're behind a proxy that's not working, try:"
    echo "  unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY"
    echo "  bash setup.sh"
    echo ""
    echo "Or configure pip proxy correctly:"
    echo "  pip config set global.proxy http://your-proxy:port"
    exit 1
}

echo ""
echo "========================================="
echo "✓ Setup complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Start the server:"
echo "   bash start.sh"
echo ""
echo "2. Or manually activate venv:"
echo "   source venv/bin/activate"
echo "   python -m uvicorn worker_router.app:app --host 0.0.0.0 --port 5000"
echo ""
