#!/bin/bash
# Run Python test with venv activated

SCRIPT_DIR="$(cd "$(dirname "$0")" && cd ../.. && pwd)"

# Check if venv exists
if [ ! -d "$SCRIPT_DIR/venv" ]; then
    echo "✗ Virtual environment not found!"
    echo "Please run: bash setup.sh"
    exit 1
fi

# Activate venv
source "$SCRIPT_DIR/venv/bin/activate"

# Change to test directory
cd "$SCRIPT_DIR/test/ez_llm_server"

# Run test
python test_generate.py
