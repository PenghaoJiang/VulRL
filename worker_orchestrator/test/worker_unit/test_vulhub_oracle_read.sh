#!/bin/bash
# Test Vulhub Read-based Oracle Mode (SQLi, LFI, etc.)

set -e

echo "========================================================================"
echo "Testing Vulhub Read-based Oracle Mode (flag extraction + vulhub_read reward)"
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
echo "Running Vulhub read-based oracle test..."
echo ""
echo "Test cases:"
echo "  - django/CVE-2021-35042 (SQLi)"
echo "  - django/CVE-2022-34265 (SQLi)"
echo "  - flink/CVE-2020-17519 (LFI)"
echo "  - coldfusion/CVE-2010-2861 (LFI)"
echo ""
echo "Run with arguments to test specific cases:"
echo "  bash test_vulhub_oracle_read.sh django-sqli"
echo "  bash test_vulhub_oracle_read.sh flink-lfi"
echo "  bash test_vulhub_oracle_read.sh coldfusion-lfi"
echo ""

# Pass arguments to Python script
python test/worker_unit/test_vulhub_oracle_read.py "$@"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Test completed successfully!"
else
    echo "✗ Test failed with exit code $EXIT_CODE"
    exit $EXIT_CODE
fi
