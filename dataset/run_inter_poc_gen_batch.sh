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
# These are real cases from vulhub with docker-compose.yml
CASES=(
  "1panel/CVE-2024-39907"
  "activemq/CVE-2015-5254"
  "activemq/CVE-2016-3088"
  "activemq/CVE-2022-41678"
  "activemq/CVE-2023-46604"
  "adminer/CVE-2021-21311"
  "adminer/CVE-2021-43008"
  "airflow/CVE-2020-11978"
  "airflow/CVE-2020-11981"
  "airflow/CVE-2020-17526"
  "aj-report/CNVD-2024-15077"
  "apache-cxf/CVE-2024-28752"
  "apache-druid/CVE-2021-25646"
  "apereo-cas/4.1-rce"
  "apisix/CVE-2020-13945"
  "apisix/CVE-2021-45232"
  "appweb/CVE-2018-8715"
  "aria2/rce"
  "bash/CVE-2014-6271"
  "cacti/CVE-2022-46169"
  "cacti/CVE-2023-39361"
  "cacti/CVE-2025-24367"
  "celery/celery3_redis_unauth"
  "cgi/CVE-2016-5385"
  "cmsms/CVE-2019-9053"
  "cmsms/CVE-2021-26120"
  "coldfusion/CVE-2010-2861"
  "coldfusion/CVE-2017-3066"
  "coldfusion/CVE-2023-26360"
  "coldfusion/CVE-2023-29300"
  "confluence/CVE-2019-3396"
  "confluence/CVE-2021-26084"
  "confluence/CVE-2022-26134"
  "confluence/CVE-2023-22515"
  "confluence/CVE-2023-22527"
  "couchdb/CVE-2017-12635"
  "couchdb/CVE-2017-12636"
  "couchdb/CVE-2022-24706"
  "craftcms/CVE-2023-41892"
  "craftcms/CVE-2024-56145"
  "craftcms/CVE-2025-32432"
  "cups-browsed/CVE-2024-47177"
  "discuz/wooyun-2010-080723"
  "discuz/x3.4-arbitrary-file-deletion"
  "django/CVE-2017-12794"
  "django/CVE-2018-14574"
  "django/CVE-2019-14234"
  "django/CVE-2020-9402"
  "django/CVE-2021-35042"
  "django/CVE-2022-34265"
)

# Result directory (inherited by child script)
export RESULT_DIR="/data1/jph/tmp/result_v4"

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
