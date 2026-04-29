"""
Step 5 integration test: verify VulhubRCEReward and VulhubReadReward correctly
fall back to ProgressDispatcher when oracle outcome fails.

Tests two key invariants:
  1. Outcome gating preserved: if oracle passes → 1.0 (unchanged)
  2. Progress fallback hits: if oracle fails AND case_id set → progress score in [0.0, 0.20]
  3. Disabled fallback: if enable_progress_fallback=False → legacy 0.0 behavior

Mocks adapter and oracle_test to isolate progress integration logic.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from worker_unit.reward.task_specific.vulhub_rce_reward import VulhubRCEReward
from worker_unit.reward.task_specific.vulhub_read_reward import VulhubReadReward


_PASS = "\033[32m✓\033[0m"
_FAIL = "\033[31m✗\033[0m"


def step(action: str, observation: str = "") -> dict:
    return {"action": action, "observation": observation}


def check(label: str, predicate, actual) -> bool:
    ok = predicate(actual)
    mark = _PASS if ok else _FAIL
    print(f"  {mark} {label:62s} got={actual}")
    return ok


# ─────────────────────────────────────────────────────────────────────
# Test 1: VulhubRCEReward — progress fallback when oracle missing
# ─────────────────────────────────────────────────────────────────────

def test_rce_progress_fallback():
    """
    No adapter / no case_dir → oracle fails internally → progress dispatcher routes by case_id.
    Use struts2/s2-045 (M05 engine-injection) with engine-injection-style payload.
    """
    print("\n[Test 1] VulhubRCEReward — progress fallback (oracle stage skipped)")
    n_pass = n_total = 0

    cfg = {
        "vulhub_path": "struts2/s2-045",
        "adapter": None,           # no adapter → oracle stage returns False internally
        "case_dir": None,
        "enable_progress_fallback": True,
    }
    reward = VulhubRCEReward(cfg)

    # T1: just OGNL syntax → 0.05
    traj_t1 = [step("curl -H 'Content-Type: %{1+1}' http://target/", "HTTP/1.1 200")]
    score = reward.compute(traj_t1, "struts2/s2-045_t1")
    n_total += 1
    if check("oracle skip + OGNL syntax → progress T1 (0.05)",
            lambda s: s == 0.05, score): n_pass += 1

    # T2: OGNL + Runtime → 0.10
    traj_t2 = [step(
        "curl -H 'Content-Type: %{(#cmd=...).(#p=new java.lang.ProcessBuilder)}' http://target/",
        "HTTP/1.1 500"
    )]
    score = reward.compute(traj_t2, "struts2/s2-045_t2")
    n_total += 1
    if check("oracle skip + OGNL+Runtime → progress T2 (0.10)",
            lambda s: s == 0.10, score): n_pass += 1

    # No engine syntax at all → 0.0
    traj_zero = [step("curl http://target/", "HTTP/1.1 200")]
    score = reward.compute(traj_zero, "struts2/s2-045_zero")
    n_total += 1
    if check("oracle skip + no engine syntax → 0.0",
            lambda s: s == 0.0, score): n_pass += 1

    print(f"  Test 1 result: {n_pass}/{n_total}")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# Test 2: VulhubReadReward — progress fallback when flag not found
# ─────────────────────────────────────────────────────────────────────

def test_read_progress_fallback():
    """
    Flag set but not found in trajectory → progress dispatcher routes by case_id.
    Use cacti/CVE-2023-39361 (M01 sql-injection).
    """
    print("\n[Test 2] VulhubReadReward — progress fallback (flag missing)")
    n_pass = n_total = 0

    cfg = {
        "vulhub_path": "cacti/CVE-2023-39361",
        "oracle_flag": "flag_xxxxxxxxxxxxxxxxxxxxxxxx",  # flag NOT in trajectory
        "enable_progress_fallback": True,
    }
    reward = VulhubReadReward(cfg)

    # T1: single SQL signature
    traj_t1 = [step("curl 'http://target/?q=test UNION SELECT 1,2'", "HTTP/1.1 200")]
    score = reward.compute(traj_t1, "cacti/CVE-2023-39361_t1")
    n_total += 1
    if check("flag-miss + UNION SELECT → progress T1 (0.05)",
            lambda s: s == 0.05, score): n_pass += 1

    # T2: multi-category SQLi
    traj_t2 = [step(
        "curl 'http://target/?q=test UNION SELECT 1,2 OR 1=1 -- '",
        "HTTP/1.1 200"
    )]
    score = reward.compute(traj_t2, "cacti/CVE-2023-39361_t2")
    n_total += 1
    if check("flag-miss + UNION+OR+comment → progress T2 (0.10)",
            lambda s: s == 0.10, score): n_pass += 1

    # T3: T2 + SQL syntax error in obs
    traj_t3 = [step(
        "curl 'http://target/?q=test UNION SELECT 1,2 OR 1=1 -- '",
        "HTTP/1.1 500\nYou have an error in your SQL syntax"
    )]
    score = reward.compute(traj_t3, "cacti/CVE-2023-39361_t3")
    n_total += 1
    if check("flag-miss + sql syntax error → progress T3 (0.15)",
            lambda s: s == 0.15, score): n_pass += 1

    print(f"  Test 2 result: {n_pass}/{n_total}")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# Test 3: Outcome gating preserved — flag found returns 1.0
# ─────────────────────────────────────────────────────────────────────

def test_read_outcome_gating():
    """When flag IS found, return 1.0 regardless of progress signals."""
    print("\n[Test 3] Outcome gating: flag found → 1.0 (progress NOT used)")
    n_pass = n_total = 0

    flag = "flag_a3f9b2x8c1y7d6z9e5q4"
    cfg = {
        "vulhub_path": "cacti/CVE-2023-39361",
        "oracle_flag": flag,
        "enable_progress_fallback": True,
    }
    reward = VulhubReadReward(cfg)

    # Flag IS in trajectory
    traj = [step(
        f"curl 'http://target/?q=test UNION SELECT 1,2'",
        f"HTTP/1.1 200\n<wrapper>{flag}</wrapper>"
    )]
    score = reward.compute(traj, "cacti/CVE-2023-39361_outcome")
    n_total += 1
    if check("flag found → 1.0 (outcome wins)",
            lambda s: s == 1.0, score): n_pass += 1

    print(f"  Test 3 result: {n_pass}/{n_total}")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# Test 4: enable_progress_fallback=False reverts to legacy 0.0
# ─────────────────────────────────────────────────────────────────────

def test_progress_disabled():
    """When progress fallback is explicitly disabled, return 0.0 on outcome miss."""
    print("\n[Test 4] enable_progress_fallback=False → legacy 0.0 behavior")
    n_pass = n_total = 0

    cfg = {
        "vulhub_path": "cacti/CVE-2023-39361",
        "oracle_flag": "flag_NOT_THERE",
        "enable_progress_fallback": False,
    }
    reward = VulhubReadReward(cfg)

    # Same T2 trajectory as Test 2 — but with progress disabled, must be 0.0
    traj = [step(
        "curl 'http://target/?q=test UNION SELECT 1,2 OR 1=1 -- '",
        "HTTP/1.1 200"
    )]
    score = reward.compute(traj, "test_disabled")
    n_total += 1
    if check("progress disabled + sql payload → 0.0 (legacy)",
            lambda s: s == 0.0, score): n_pass += 1

    print(f"  Test 4 result: {n_pass}/{n_total}")
    return n_pass, n_total


# ─────────────────────────────────────────────────────────────────────
# Test 5: Unknown case_id falls back to 0.0 cleanly
# ─────────────────────────────────────────────────────────────────────

def test_unknown_case_falls_back_to_zero():
    """Case_id not in yaml → progress returns 0.0 (no crash)."""
    print("\n[Test 5] Unknown case_id → 0.0 (graceful fallback)")
    n_pass = n_total = 0

    cfg = {
        "vulhub_path": "totally/fake-cve",
        "oracle_flag": "flag_NOT_THERE",
        "enable_progress_fallback": True,
    }
    reward = VulhubReadReward(cfg)

    traj = [step("curl 'http://target/?q=test UNION SELECT'", "HTTP/1.1 200")]
    score = reward.compute(traj, "fake_case")
    n_total += 1
    if check("unknown case → 0.0", lambda s: s == 0.0, score): n_pass += 1

    print(f"  Test 5 result: {n_pass}/{n_total}")
    return n_pass, n_total


def main():
    print("=" * 78)
    print("Step 5 Integration Tests: ProgressDispatcher → vulhub_*_reward")
    print("=" * 78)

    p1, t1 = test_rce_progress_fallback()
    p2, t2 = test_read_progress_fallback()
    p3, t3 = test_read_outcome_gating()
    p4, t4 = test_progress_disabled()
    p5, t5 = test_unknown_case_falls_back_to_zero()

    total_pass = p1 + p2 + p3 + p4 + p5
    total_n = t1 + t2 + t3 + t4 + t5

    print("\n" + "=" * 78)
    print(f"INTEGRATION TESTS: {total_pass}/{total_n} passed")
    print("=" * 78)
    return 0 if total_pass == total_n else 1


if __name__ == "__main__":
    sys.exit(main())
