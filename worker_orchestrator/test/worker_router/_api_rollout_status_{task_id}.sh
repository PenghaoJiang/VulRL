#!/bin/bash
# Test GET /api/rollout/status/{task_id}
# Usage: ./_api_rollout_status_{task_id}.sh <task_id>
# Example: ./_api_rollout_status_{task_id}.sh 550e8400-e29b-41d4-a716-446655440000

TASK_ID=${1:-"8701e8b4-596a-4530-9a78-c1ae096e50a1"}

curl -X GET "http://localhost:5000/api/rollout/status/${TASK_ID}"
echo ""
