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

# Function to check if a package is installed
check_package() {
    python3 -c "import $1" 2>/dev/null
    return $?
}

# Function to check package version
check_package_version() {
    pip show "$1" 2>/dev/null | grep -q "Version:"
    return $?
}

# Install dependencies with smart checking
echo "Checking and installing dependencies..."
echo ""

# Key packages to check (avoids reinstalling heavy dependencies)
CRITICAL_PACKAGES=(
    "fastapi:fastapi"
    "uvicorn:uvicorn"
    "redis:redis"
    "aiohttp:aiohttp"
    "docker:docker"
    "pandas:pandas"
    "pyarrow:pyarrow"
    "pydantic:pydantic"
)

MISSING_PACKAGES=()
INSTALLED_COUNT=0

# Check which packages are missing
for pkg_spec in "${CRITICAL_PACKAGES[@]}"; do
    IFS=':' read -r import_name pip_name <<< "$pkg_spec"
    if check_package "$import_name"; then
        echo "✓ $pip_name already installed"
        INSTALLED_COUNT=$((INSTALLED_COUNT + 1))
    else
        echo "✗ $pip_name not found, will install"
        MISSING_PACKAGES+=("$pip_name")
    fi
done

echo ""

# Install all dependencies if many are missing (faster than selective install)
if [ ${#MISSING_PACKAGES[@]} -gt 3 ] || [ $INSTALLED_COUNT -eq 0 ]; then
    echo "Installing all dependencies from requirements.txt..."
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
# Install only missing packages (saves time)
elif [ ${#MISSING_PACKAGES[@]} -gt 0 ]; then
    echo "Installing missing packages: ${MISSING_PACKAGES[*]}"
    for pkg in "${MISSING_PACKAGES[@]}"; do
        # Get version from requirements.txt
        version=$(grep "^${pkg}==" requirements.txt | head -1)
        if [ -n "$version" ]; then
            echo "Installing $version..."
            pip install "$version" --no-cache-dir || {
                echo "Warning: Failed to install $version, trying full requirements.txt..."
                pip install -r requirements.txt --no-cache-dir
                break
            }
        else
            echo "Installing $pkg (latest)..."
            pip install "$pkg" --no-cache-dir
        fi
    done
else
    echo "✓ All dependencies already satisfied!"
    echo "Verifying with requirements.txt..."
    pip install -r requirements.txt --no-cache-dir --no-deps || {
        echo "Warning: Some version mismatches detected, reinstalling..."
        pip install -r requirements.txt --no-cache-dir
    }
fi

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
