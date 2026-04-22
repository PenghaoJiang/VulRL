#!/bin/bash
# Test Vulhub RCE Oracle Mode (File Creation)

set -e

echo "========================================================================"
echo "Testing Vulhub RCE Oracle Mode (oracle_solution.sh + vulhub_rce reward)"
echo "========================================================================"
echo ""

# Get script directory and project root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

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

# Note: Oracle mode does not require LLM server (it uses oracle_solution.sh)
echo "Note: Oracle mode enabled - LLM server not required"
echo ""

# Check if docker is available
echo "Checking Docker..."
if ! docker --version > /dev/null 2>&1; then
    echo "✗ Docker not found!"
    echo ""
    echo "Please install Docker first"
    exit 1
fi
echo "✓ Docker is available"

# Check if docker compose is available
if docker compose version > /dev/null 2>&1; then
    echo "✓ Docker Compose (plugin) is available"
elif docker-compose version > /dev/null 2>&1; then
    echo "✓ Docker Compose (standalone) is available"
else
    echo "✗ Docker Compose not found!"
    echo ""
    echo "Please install Docker Compose first"
    exit 1
fi

echo ""

# Run test
echo "Running Vulhub RCE oracle test..."
echo ""

python test/worker_unit/test_vulhub_oracle_rce.py

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Test completed successfully!"
else
    echo "✗ Test failed with exit code $EXIT_CODE"
    exit $EXIT_CODE
fi
