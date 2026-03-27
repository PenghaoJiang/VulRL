#!/bin/bash
# Run all test scripts in sequence

echo "========================================="
echo "Worker Router API Test Suite"
echo "========================================="
echo ""

echo "1. Testing root endpoint (GET /)..."
./_.sh
echo ""

echo "2. Testing health check (GET /health)..."
./_health.sh
echo ""

echo "3. Testing rollout execution (POST /api/rollout/execute)..."
RESPONSE=$(./_api_rollout_execute.sh)
echo "$RESPONSE"
# Extract task_id from response (requires jq)
if command -v jq &> /dev/null; then
    TASK_ID=$(echo "$RESPONSE" | jq -r '.task_id')
    echo "Extracted task_id: $TASK_ID"
else
    echo "Note: Install 'jq' to auto-extract task_id"
    TASK_ID="replace-with-actual-task-id"
fi
echo ""

echo "4. Testing workers status (GET /api/workers/status)..."
WORKERS_RESPONSE=$(./_api_workers_status.sh)
echo "$WORKERS_RESPONSE"
# Extract worker_id from response (requires jq)
if command -v jq &> /dev/null; then
    WORKER_ID=$(echo "$WORKERS_RESPONSE" | jq -r '.workers[0].worker_id // "no-workers"')
    echo "Extracted worker_id: $WORKER_ID"
else
    WORKER_ID="replace-with-actual-worker-id"
fi
echo ""

echo "5. Testing rollout status (GET /api/rollout/status/{task_id})..."
if [ "$TASK_ID" != "replace-with-actual-task-id" ]; then
    ./_api_rollout_status_{task_id}.sh "$TASK_ID"
else
    echo "Skipping: No valid task_id (use: ./_api_rollout_status_{task_id}.sh <task_id>)"
fi
echo ""

echo "6. Testing worker shutdown (POST /api/workers/{worker_id}/shutdown)..."
echo "Skipping: Uncomment to test worker shutdown"
# if [ "$WORKER_ID" != "no-workers" ] && [ "$WORKER_ID" != "replace-with-actual-worker-id" ]; then
#     ./_api_workers_{worker_id}_shutdown.sh "$WORKER_ID"
# else
#     echo "Skipping: No valid worker_id (use: ./_api_workers_{worker_id}_shutdown.sh <worker_id>)"
# fi
echo ""

echo "========================================="
echo "Test suite completed!"
echo "========================================="
echo ""
echo "Next steps:"
echo "1. Check logs: ../../logs/worker_router.log"
echo "2. View API docs: http://localhost:5000/docs"
echo "3. Test individual endpoints as needed"
