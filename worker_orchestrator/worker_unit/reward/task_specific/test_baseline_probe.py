"""
Step 6.3: Unit tests for make_side_effect_probe baseline-diff logic.

Mocks a VulhubAdapter-like object with:
  - target_container_obj.exec_run(...) → fake (output bytes)
  - baseline_marker_path
  - baseline_pid_set

Tests verify:
  1. Baseline-diff path: new files in /tmp → probe True
  2. Baseline-diff path: new sh-like process → probe True
  3. Baseline-diff path: only marker itself in find output → probe False
  4. Baseline-diff path: only kernel/system processes added → probe False
  5. Heuristic fallback: no baseline + canonical marker exists → probe True
  6. Heuristic fallback: no baseline + no marker → probe False
  7. None adapter → probe is None
"""

import sys
from pathlib import Path
from typing import List

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from worker_unit.reward.task_specific.vulhub_progress_helper import (
    make_side_effect_probe,
)


_PASS = "\033[32m✓\033[0m"
_FAIL = "\033[31m✗\033[0m"


class FakeExecResult:
    def __init__(self, output_bytes: bytes):
        self.output = output_bytes


class FakeContainer:
    """Minimal fake of docker.models.containers.Container for probe tests.

    Stores a sequence of bytes payloads to return for exec_run calls in order.
    """
    def __init__(self, scripted_outputs: List[bytes]):
        self._outputs = list(scripted_outputs)

    def exec_run(self, *args, **kwargs):
        if not self._outputs:
            return FakeExecResult(b"")
        return FakeExecResult(self._outputs.pop(0))


class FakeAdapter:
    def __init__(self, target_container_obj=None,
                 baseline_marker_path=None,
                 baseline_pid_set=None):
        self.target_container_obj = target_container_obj
        self.baseline_marker_path = baseline_marker_path
        self.baseline_pid_set = baseline_pid_set


def check(label, predicate, actual):
    ok = predicate(actual)
    print(f"  {_PASS if ok else _FAIL} {label:62s} got={actual}")
    return ok


def test_baseline_diff_new_files():
    """Baseline path: find returns new file → probe True."""
    print("\n[1] Baseline-diff: new file in /tmp → True")
    container = FakeContainer([
        b"/tmp/exploit.txt\n",          # 1st call: find -newer marker → has file
        b"123 sh\n456 bash\n",          # 2nd call: ps (won't be reached if first hit)
    ])
    adapter = FakeAdapter(
        target_container_obj=container,
        baseline_marker_path="/tmp/.vulrl_marker_x",
        baseline_pid_set={("1", "init"), ("78", "java")},
    )
    probe = make_side_effect_probe(adapter)
    return check("new file → True", lambda x: x is True, probe())


def test_baseline_diff_new_process():
    """Baseline path: process diff produces sh-like new process → True."""
    print("\n[2] Baseline-diff: new sh process not in baseline → True")
    container = FakeContainer([
        b"",                                                    # find: empty (no new files)
        b"1 init\n78 java\n300 sh\n",                          # ps: new pid 300 sh
    ])
    adapter = FakeAdapter(
        target_container_obj=container,
        baseline_marker_path="/tmp/.vulrl_marker_x",
        baseline_pid_set={("1", "init"), ("78", "java")},
    )
    probe = make_side_effect_probe(adapter)
    return check("new sh process → True", lambda x: x is True, probe())


def test_baseline_diff_marker_only():
    """Baseline path: find returns only the marker itself → False."""
    print("\n[3] Baseline-diff: find returns only marker → False")
    container = FakeContainer([
        b"/tmp/.vulrl_marker_x\n",                       # find: only marker
        b"1 init\n78 java\n",                            # ps: same as baseline
    ])
    adapter = FakeAdapter(
        target_container_obj=container,
        baseline_marker_path="/tmp/.vulrl_marker_x",
        baseline_pid_set={("1", "init"), ("78", "java")},
    )
    probe = make_side_effect_probe(adapter)
    return check("only marker in find → False", lambda x: x is False, probe())


def test_baseline_diff_kernel_processes_ignored():
    """Baseline path: new processes are kernel-thread-like, not suspicious → False."""
    print("\n[4] Baseline-diff: new but non-suspicious process → False")
    container = FakeContainer([
        b"",                                                  # find: empty
        b"1 init\n78 java\n200 [kworker/0:1]\n",            # ps: new but kthread
    ])
    adapter = FakeAdapter(
        target_container_obj=container,
        baseline_marker_path="/tmp/.vulrl_marker_x",
        baseline_pid_set={("1", "init"), ("78", "java")},
    )
    probe = make_side_effect_probe(adapter)
    return check("new kworker → False (not suspicious)", lambda x: x is False, probe())


def test_heuristic_fallback_marker_present():
    """No baseline: heuristic path checks /tmp/exploit.txt → True."""
    print("\n[5] Heuristic fallback: /tmp/exploit.txt exists → True")
    container = FakeContainer([
        b"HIT\n",        # heuristic test command returns HIT
    ])
    adapter = FakeAdapter(
        target_container_obj=container,
        baseline_marker_path=None,        # NO baseline
        baseline_pid_set=None,
    )
    probe = make_side_effect_probe(adapter)
    return check("heuristic HIT → True", lambda x: x is True, probe())


def test_heuristic_fallback_no_marker():
    """No baseline: heuristic path no marker → False."""
    print("\n[6] Heuristic fallback: no canonical marker → False")
    container = FakeContainer([
        b"MISS\n",
    ])
    adapter = FakeAdapter(
        target_container_obj=container,
        baseline_marker_path=None,
        baseline_pid_set=None,
    )
    probe = make_side_effect_probe(adapter)
    return check("heuristic MISS → False", lambda x: x is False, probe())


def test_none_adapter():
    """None adapter → probe is None (not callable)."""
    print("\n[7] None adapter → probe is None")
    probe = make_side_effect_probe(None)
    return check("None adapter → None probe", lambda x: x is None, probe)


def test_baseline_only_partial():
    """Only baseline_pid_set set (no marker) — should still work for process diff."""
    print("\n[8] Partial baseline: only pid_set, find skipped, new sh → True")
    container = FakeContainer([
        # Only one call expected: ps (since marker is None, file-diff path skipped)
        b"1 init\n78 java\n300 bash\n",
    ])
    adapter = FakeAdapter(
        target_container_obj=container,
        baseline_marker_path=None,                  # no marker
        baseline_pid_set={("1", "init"), ("78", "java")},
    )
    probe = make_side_effect_probe(adapter)
    return check("only pid baseline + new bash → True", lambda x: x is True, probe())


def main():
    print("=" * 72)
    print("Step 6.3 Tests: make_side_effect_probe baseline-diff logic")
    print("=" * 72)

    results = [
        test_baseline_diff_new_files(),
        test_baseline_diff_new_process(),
        test_baseline_diff_marker_only(),
        test_baseline_diff_kernel_processes_ignored(),
        test_heuristic_fallback_marker_present(),
        test_heuristic_fallback_no_marker(),
        test_none_adapter(),
        test_baseline_only_partial(),
    ]
    n_pass = sum(1 for r in results if r)
    n_total = len(results)

    print("\n" + "=" * 72)
    print(f"BASELINE PROBE TESTS: {n_pass}/{n_total} passed")
    print("=" * 72)
    return 0 if n_pass == n_total else 1


if __name__ == "__main__":
    sys.exit(main())
