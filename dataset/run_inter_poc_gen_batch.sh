#!/bin/bash

# ============================================================================
# Batch PoC Generation Script
# ============================================================================
# This script runs multiple cases by setting CVE_PATH and calling 
# run_inter_poc_gen.sh for each case.
#
# Usage: bash run_inter_poc_gen_batch.sh
# ============================================================================

# ============================================================================
# Configuration
# ============================================================================
# Define cases to process (format: category/cve_id)
CASES=(
  "couchdb/CVE-2017-12635"
  "apache/CVE-2021-41773"
  "aj-report/CNVD-2024-15077"
  # Add more cases here
)

# Result directory (inherited by child script)
export RESULT_DIR="/data1/jph/tmp/result_v3"

# ============================================================================
# Batch Processing
# ============================================================================
TOTAL=${#CASES[@]}
SUCCESS=0
FAILED=0

echo "=========================================="
echo "Batch PoC Generation"
echo "=========================================="
echo "Total cases: ${TOTAL}"
echo "Result directory: ${RESULT_DIR}"
echo ""

for i in "${!CASES[@]}"; do
  CASE="${CASES[$i]}"
  INDEX=$((i + 1))
  
  echo ""
  echo "=========================================="
  echo "[${INDEX}/${TOTAL}] Processing: ${CASE}"
  echo "=========================================="
  
  # Export CVE_PATH for the child script
  export CVE_PATH="${CASE}"
  
  # Run the single-case script
  bash run_inter_poc_gen.sh
  
  # Check exit status
  if [ $? -eq 0 ]; then
    SUCCESS=$((SUCCESS + 1))
    echo "[${INDEX}/${TOTAL}] ✓ SUCCESS: ${CASE}"
  else
    FAILED=$((FAILED + 1))
    echo "[${INDEX}/${TOTAL}] ✗ FAILED: ${CASE}"
  fi
done

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "=========================================="
echo "Batch Processing Complete"
echo "=========================================="
echo "Total:   ${TOTAL}"
echo "Success: ${SUCCESS}"
echo "Failed:  ${FAILED}"
echo ""
echo "Results saved to: ${RESULT_DIR}"
