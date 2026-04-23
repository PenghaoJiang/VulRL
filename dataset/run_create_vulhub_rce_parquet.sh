#!/bin/bash
# Create Vulhub Oracle Parquet for Training
#
# This script generates parquet files from oracle-verified Vulhub cases.
# Supports both RCE (vulhub_rce) and Read (vulhub_read) reward types.
# Can generate easy, medium, or hard difficulty levels.

set -e

echo "========================================================================"
echo "Vulhub Oracle Parquet Creator"
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
OUTPUT_FILE="${OUTPUT_FILE:-$SCRIPT_DIR/train_vulhub.parquet}"
BENCHMARK_ROOT="${BENCHMARK_ROOT:-$REPO_ROOT/benchmark/vulhub}"
DIFFICULTY="${DIFFICULTY:-easy}"

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --difficulty)
            DIFFICULTY="$2"
            shift 2
            ;;
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --input)
            INPUT_FILE="$2"
            shift 2
            ;;
        --benchmark-root)
            BENCHMARK_ROOT="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --difficulty <easy|medium|hard>  Prompt difficulty (default: easy)"
            echo "  --output <path>                  Output parquet file"
            echo "  --input <path>                   Input test list file"
            echo "  --benchmark-root <path>          Benchmark root directory"
            echo "  -h, --help                       Show this help"
            echo ""
            echo "Examples:"
            echo "  $0                                    # Create train_vulhub_easy.parquet"
            echo "  $0 --difficulty medium                # Create train_vulhub_medium.parquet"
            echo "  $0 --difficulty hard --output out.parquet  # Create out_hard.parquet"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Validate difficulty
if [[ ! "$DIFFICULTY" =~ ^(easy|medium|hard)$ ]]; then
    echo "✗ Invalid difficulty: $DIFFICULTY"
    echo "  Must be one of: easy, medium, hard"
    exit 1
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
echo "  Output:         $OUTPUT_FILE (will auto-append _$DIFFICULTY)"
echo "  Benchmark Root: $BENCHMARK_ROOT"
echo "  Difficulty:     $DIFFICULTY"
echo ""

# Run the Python script
echo "Creating parquet..."
echo ""

python create_vulhub_rce_parquet.py \
    --input "$INPUT_FILE" \
    --output "$OUTPUT_FILE" \
    --benchmark-root "$BENCHMARK_ROOT" \
    --difficulty "$DIFFICULTY"

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    # Get actual output filename (with difficulty appended)
    OUTPUT_STEM=$(basename "$OUTPUT_FILE" .parquet)
    OUTPUT_DIR=$(dirname "$OUTPUT_FILE")
    ACTUAL_OUTPUT="$OUTPUT_DIR/${OUTPUT_STEM}_${DIFFICULTY}.parquet"
    
    echo "✓ Parquet created successfully: $ACTUAL_OUTPUT"
    echo ""
    echo "Next steps:"
    echo "  1. Copy to worker_orchestrator for use with SkyRL:"
    echo "     cp $ACTUAL_OUTPUT $REPO_ROOT/worker_orchestrator/ez_generator/"
    echo ""
    echo "  2. Use in SkyRL training config:"
    echo "     dataset_path: worker_orchestrator/ez_generator/$(basename $ACTUAL_OUTPUT)"
    echo ""
    echo "To create other difficulty levels:"
    echo "  $0 --difficulty easy     # Create easy prompts"
    echo "  $0 --difficulty medium   # Create medium prompts"
    echo "  $0 --difficulty hard     # Create hard prompts"
else
    echo "✗ Failed to create parquet (exit code: $EXIT_CODE)"
    exit $EXIT_CODE
fi
