#!/bin/bash

# Activate virtual environment
source /data1/jph/VulRL/.venv/bin/activate

# Load API key
export OPENAI_API_KEY=$(cat /data1/jph/apikey.txt)
# export OPENAI_API_BASE="https://api.openai.com/v1"  # Optional, defaults to OpenAI

# ============================================================================
# Configuration
# ============================================================================
# Can be overridden by exporting CVE_PATH before calling this script
CVE_PATH="${CVE_PATH:-couchdb/CVE-2017-12635}"  # Format: category/cve_id
RESULT_DIR="${RESULT_DIR:-/data1/jph/tmp/result_v3}"

# Convert to flat folder name
FOLDER_NAME=$(echo "$CVE_PATH" | tr '/' '_')  # "couchdb_CVE-2017-12635"

# # Clean previous results for this CVE
# rm -rf "${RESULT_DIR}/${FOLDER_NAME}"

# ============================================================================
# Run test
# ============================================================================
echo "========== Test: ${CVE_PATH} =========="
python interactive_poc_generator.py \
  --vulhub-dir /data1/jph/vulhub \
  --cve-filter "${CVE_PATH}" \
  --result-dir "${RESULT_DIR}" \
  --max-steps 30 \
  --service-wait 600

# ============================================================================
# Verify output
# ============================================================================
echo ""
echo "========== Verifying Output =========="
CVE_RESULT_DIR="${RESULT_DIR}/${FOLDER_NAME}"

# Check generated files
echo "[1] Generated files:"
ls -la "$CVE_RESULT_DIR/" 2>/dev/null || echo "  ERROR: Result directory not found"

# Check trajectory for Phase/Step markers
echo ""
echo "[2] Phase and Step markers in trajectory:"
python3 -c "
import json, sys
traj_file = '${CVE_RESULT_DIR}/agent_1_traj.json'
try:
    traj = json.load(open(traj_file))
    for msg in traj:
        content = msg.get('content', '')
        if isinstance(content, str) and ('[Phase' in content or '[Step' in content or '[Prep' in content):
            print(f'  {content[:200]}')
    print(f'  Total messages in trajectory: {len(traj)}')
except Exception as e:
    print(f'  ERROR: {e}')
"

# Check poc.py exists and has content
echo ""
echo "[3] poc.py preview (first 10 lines):"
head -10 "$CVE_RESULT_DIR/poc.py" 2>/dev/null || echo "  ERROR: poc.py not found"

echo ""
echo "========== Test Complete =========="
