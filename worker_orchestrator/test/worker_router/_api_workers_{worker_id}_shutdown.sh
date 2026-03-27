#!/bin/bash
# Test POST /api/workers/{worker_id}/shutdown
# Usage: ./_api_workers_{worker_id}_shutdown.sh <worker_id>
# Example: ./_api_workers_{worker_id}_shutdown.sh worker-abc123

WORKER_ID=${1:-"6a830bac"}

curl -X POST "http://localhost:5000/api/workers/${WORKER_ID}/shutdown"
echo ""
