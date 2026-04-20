#!/bin/bash
# Create Vulhub RCE Oracle Parquet for Training
#
# This script generates a parquet file from oracle-verified Vulhub RCE cases.
# The parquet is designed for training with vulhub_rce reward (oracle_test.sh verification).

set -e

echo "========================================================================"
echo "Vulhub RCE Oracle Parquet Creator"
echo "========================================================================"
echo ""

# Get script directory and repo root
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$SCRIPT_DIR"

# Check if virtual environment exists
if [ ! -d "$REPO_ROOT/.venv" ]; then
    echo "✗ Virtual environment not found at $REPO_ROOT/.venv"
    echo ""
    echo "Please create virtual environment first:"
    echo "  cd $REPO_ROOT"
    echo "  python3 -m venv .venv"
    echo "  source .venv/bin/activate"
    echo "  pip install pandas pyarrow"
    exit 1
fi

# Activate virtual environment
echo "Activating virtual environment..."
source "$REPO_ROOT/.venv/bin/activate"

# Verify pandas is installed
if ! python -c "import pandas" 2>/dev/null; then
    echo "✗ pandas not installed!"
    echo ""
    echo "Please install dependencies:"
    echo "  pip install pandas pyarrow"
    exit 1
fi

echo "✓ Virtual environment activated"
echo ""

# Set default paths
INPUT_FILE="${INPUT_FILE:-$REPO_ROOT/vulhub_oracle_and_test/full_test_lists.sh}"
OUTPUT_FILE="${OUTPUT_FILE:-$SCRIPT_DIR/train_vulhub_rce.parquet}"
BENCHMARK_ROOT="${BENCHMARK_ROOT:-$REPO_ROOT/benchmark/vulhub}"

# Allow overriding via arguments
if [ ! -z "$1" ]; then
    OUTPUT_FILE="$1"
fi

# Check if input file exists
if [ ! -f "$INPUT_FILE" ]; then
    echo "✗ Input file not found: $INPUT_FILE"
    echo ""
    echo "Please ensure vulhub_oracle_and_test/full_test_lists.sh exists"
    exit 1
fi

# Check if benchmark root exists
if [ ! -d "$BENCHMARK_ROOT" ]; then
    echo "✗ Benchmark root not found: $BENCHMARK_ROOT"
    echo ""
    echo "Please ensure benchmark/vulhub directory exists"
    exit 1
fi

echo "Configuration:"
echo "  Input:          $INPUT_FILE"
echo "  Output:         $OUTPUT_FILE"
echo "  Benchmark Root: $BENCHMARK_ROOT"
echo ""

# Run the Python script
echo "Creating parquet..."
echo ""

python create_vulhub_rce_parquet.py \
    --input "$INPUT_FILE" \
    --output "$OUTPUT_FILE" \
    --benchmark-root "$BENCHMARK_ROOT"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✓ Parquet created successfully!"
    echo ""
    echo "Next steps:"
    echo "  1. Copy to worker_orchestrator for use with SkyRL:"
    echo "     cp $OUTPUT_FILE $REPO_ROOT/worker_orchestrator/ez_generator/"
    echo ""
    echo "  2. Use in SkyRL training config:"
    echo "     dataset_path: worker_orchestrator/ez_generator/train_vulhub_rce.parquet"
else
    echo "✗ Failed to create parquet (exit code: $EXIT_CODE)"
    exit $EXIT_CODE
fi
