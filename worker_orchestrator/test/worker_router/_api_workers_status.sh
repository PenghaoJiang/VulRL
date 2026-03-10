#!/bin/bash
# Test GET /api/workers/status

curl -X GET http://localhost:5000/api/workers/status
echo ""
