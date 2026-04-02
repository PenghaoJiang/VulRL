#!/bin/bash

# ============================================================================
# Remove False Positive Cases Script
# ============================================================================
# This script removes all false positive cases identified in the validation
# process. These cases have verify.py marked as True but Agent 1 failed to
# actually achieve the exploit.
#
# Usage: bash remove_false_positives.sh [--dry-run]
# ============================================================================

# ============================================================================
# Configuration
# ============================================================================
# Result directory (where case folders are located)
RESULT_DIR="/data1/jph/tmp/result_v4"

# False positive cases to remove (vulhub_path format)
# These are cases where verify.py says True BUT Agent 1 failed
FALSE_POSITIVES=(
  "activemq/CVE-2016-3088"
  "adminer/CVE-2021-21311"
  "apisix/CVE-2021-45232"
  "aria2/rce"
  "docker/unauthorized-rce"
  "ecshop/xianzhi-2017-02-82239600"
  "fastjson/1.2.24-rce"
  "flink/CVE-2020-17518"
  "geoserver/CVE-2021-40822"
  "geoserver/CVE-2024-36401"
  "ghostscript/CVE-2019-6116"
  "gitlist/CVE-2018-1000533"
  "httpd/apache_parsing_vulnerability"
  "java/rmi-codebase"
  "jenkins/CVE-2018-1000861"
  "jmeter/CVE-2018-1297"
  "jupyter/notebook-rce"
  "metersphere/plugin-rce"
  "mojarra/jsf-viewstate-deserialization"
  "nexus/CVE-2019-7238"
  "ofbiz/CVE-2023-49070"
  "ofbiz/CVE-2024-45507"
  "openfire/CVE-2023-32315"
  "openssh/CVE-2018-15473"
  "opentsdb/CVE-2023-25826"
  "pdfjs/CVE-2024-4367"
  "php/CVE-2018-19518"
  "phpmyadmin/CVE-2018-12613"
  "python/PIL-CVE-2018-16509"
  "python/unpickle"
  "rocketmq/CVE-2023-33246"
  "rocketmq/CVE-2023-37582"
  "saltstack/CVE-2020-16846"
  "solr/CVE-2017-12629-RCE"
  "solr/CVE-2019-0193"
  "spark/unacc"
  "spring/CVE-2016-4977"
  "spring/CVE-2017-8046"
  "spring/CVE-2018-1270"
  "spring/CVE-2018-1273"
  "spring/CVE-2022-22963"
  "spring/CVE-2022-22965"
  "struts2/s2-052"
  "struts2/s2-059"
  "struts2/s2-066"
  "struts2/s2-067"
  "supervisor/CVE-2017-11610"
  "thinkphp/2-rce"
  "tomcat/CVE-2017-12615"
  "unomi/CVE-2020-13942"
  "vite/CVE-2025-30208"
  "weblogic/CVE-2017-10271"
  "weblogic/CVE-2020-14882"
)

# ============================================================================
# Parse Arguments
# ============================================================================
DRY_RUN=false
if [ "$1" == "--dry-run" ]; then
  DRY_RUN=true
  echo "=========================================="
  echo "DRY RUN MODE - No files will be deleted"
  echo "=========================================="
  echo ""
fi

# ============================================================================
# Convert vulhub_path to folder_name
# ============================================================================
convert_to_folder_name() {
  echo "$1" | tr '/' '_'
}

# ============================================================================
# Remove Cases
# ============================================================================
TOTAL=${#FALSE_POSITIVES[@]}
REMOVED=0
FAILED=0
NOT_FOUND=0

echo "=========================================="
echo "Removing False Positive Cases"
echo "=========================================="
echo "Total cases: ${TOTAL}"
echo "Result directory: ${RESULT_DIR}"
echo ""

for i in "${!FALSE_POSITIVES[@]}"; do
  VULHUB_PATH="${FALSE_POSITIVES[$i]}"
  FOLDER_NAME=$(convert_to_folder_name "${VULHUB_PATH}")
  FOLDER_PATH="${RESULT_DIR}/${FOLDER_NAME}"
  INDEX=$((i + 1))
  
  echo "[${INDEX}/${TOTAL}] ${VULHUB_PATH} -> ${FOLDER_NAME}"
  
  if [ ! -d "${FOLDER_PATH}" ]; then
    echo "  ⚠ Not found: ${FOLDER_PATH}"
    NOT_FOUND=$((NOT_FOUND + 1))
    continue
  fi
  
  if [ "$DRY_RUN" = true ]; then
    echo "  [DRY RUN] Would remove: ${FOLDER_PATH}"
    REMOVED=$((REMOVED + 1))
  else
    if rm -rf "${FOLDER_PATH}"; then
      echo "  ✓ Removed: ${FOLDER_PATH}"
      REMOVED=$((REMOVED + 1))
    else
      echo "  ✗ Failed to remove: ${FOLDER_PATH}"
      FAILED=$((FAILED + 1))
    fi
  fi
done

# ============================================================================
# Summary
# ============================================================================
echo ""
echo "=========================================="
echo "Removal Complete"
echo "=========================================="
echo "Total:     ${TOTAL}"
echo "Removed:   ${REMOVED}"
echo "Not found: ${NOT_FOUND}"
echo "Failed:    ${FAILED}"
echo ""

if [ "$DRY_RUN" = true ]; then
  echo "This was a DRY RUN. No files were actually deleted."
  echo "Run without --dry-run to actually remove the folders."
  echo ""
fi

exit 0
