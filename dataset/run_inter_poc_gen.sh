#!/bin/bash

# Activate virtual environment
source /data1/jph/VulRL/.venv/bin/activate

# Load API key
export OPENAI_API_KEY=$(cat /data1/jph/apikey.txt)
# export OPENAI_API_BASE="https://api.openai.com/v1"  # Optional, defaults to OpenAI

# Run the PoC generator
python interactive_poc_generator.py \
  --vulhub-dir ~/vulhub \
  --cve-filter "CVE-2021-34371" \
  --result-dir /data1/jph/tmp/result_v2