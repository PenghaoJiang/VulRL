"""
Shared helper for integrating ProgressDispatcher into vulhub_rce_reward and
vulhub_read_reward.

Provides:
  - get_dispatcher(): cached singleton ProgressDispatcher, loaded from
                      vulhub_oracle_and_test/case_to_signature.yaml
  - make_side_effect_probe(adapter): build optional side_effect callable
                                     from a VulhubAdapter (RCE-only)
  - compute_progress_or_zero(case_id, trajectory, ...): convenience wrapper
                                                        that returns a float
"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from worker_unit.reward.progress import ProgressDispatcher


# Repo layout (computed once at import):
#   <repo_root>/worker_orchestrator/worker_unit/reward/task_specific/<this file>
#   <repo_root>/vulhub_oracle_and_test/case_to_signature.yaml
_THIS_FILE = Path(__file__).resolve()
_REPO_ROOT = _THIS_FILE.parent.parent.parent.parent.parent
_DEFAULT_YAML_PATH = _REPO_ROOT / "vulhub_oracle_and_test" / "case_to_signature.yaml"


@lru_cache(maxsize=1)
def get_dispatcher(yaml_path: Optional[str] = None) -> Optional[ProgressDispatcher]:
    """
    Get cached singleton ProgressDispatcher.

    Args:
        yaml_path: Optional override of yaml location (string for hashability).
                   Default: <repo_root>/vulhub_oracle_and_test/case_to_signature.yaml

    Returns:
        ProgressDispatcher instance, or None if yaml not found.
        Returning None lets callers gracefully skip progress reward.
    """
    path = Path(yaml_path) if yaml_path else _DEFAULT_YAML_PATH
    if not path.exists():
        print(f"[vulhub_progress_helper] WARNING: yaml not found at {path}; "
              f"progress reward disabled.")
        return None
    try:
        d = ProgressDispatcher(path)
        print(f"[vulhub_progress_helper] Loaded {d.case_count} cases from {path}")
        return d
    except Exception as e:
        print(f"[vulhub_progress_helper] ERROR loading dispatcher: {e}; "
              f"progress reward disabled.")
        return None


# Process names commonly spawned by RCE that DON'T appear at setup time.
# Used by baseline-diff probe to identify suspicious new processes.
_SUSPICIOUS_PROCESS_NAMES = {
    "sh", "bash", "dash", "zsh", "ksh",
    "nc", "ncat", "netcat",
    "curl", "wget",
    "python", "python2", "python3", "perl", "ruby", "php",
    "node", "nodejs",
    "socat", "ssh-keygen",
}


def make_side_effect_probe(adapter) -> Optional[Callable[[], bool]]:
    """
    Build an optional side_effect callable from a VulhubAdapter.

    Used by M05/M06/M07/M10 to detect runtime container state changes that
    indicate the agent successfully exploited (even if oracle_test didn't pass).

    Detection strategy (Step 6, baseline-diff):
      1. PRIMARY:  if adapter has baseline (marker file + pid_set), diff:
         - new files in /tmp newer than marker
         - new processes whose comm is in _SUSPICIOUS_PROCESS_NAMES
                       and whose (pid, comm) was NOT in baseline_pid_set
         Either signal triggers True.

      2. FALLBACK: if adapter has no baseline (e.g., setup didn't capture),
         fall back to canonical-marker heuristic (/tmp/exploit.txt etc.)

      3. None: if adapter is None or container is None.

    Returns:
        callable() -> bool, or None if adapter unavailable.
    """
    if not adapter:
        return None

    def probe() -> bool:
        try:
            container = getattr(adapter, "target_container_obj", None)
            if container is None:
                return False

            baseline_marker = getattr(adapter, "baseline_marker_path", None)
            baseline_pids = getattr(adapter, "baseline_pid_set", None)

            # ───────── Path 1: baseline-diff (preferred) ─────────
            if baseline_marker:
                # 1a. New files in /tmp newer than baseline marker
                cmd = f"find /tmp -newer {baseline_marker} -type f 2>/dev/null | head -5"
                res = container.exec_run(["sh", "-c", cmd], demux=False)
                out = res.output.decode("utf-8", errors="replace") if isinstance(res.output, bytes) else (res.output or "")
                # Strip the marker itself (in case find returns it on some FS)
                new_files = [
                    line for line in out.splitlines()
                    if line.strip() and line.strip() != baseline_marker
                ]
                if new_files:
                    return True

            if baseline_pids is not None:
                # 1b. New processes vs baseline
                res = container.exec_run(
                    ["sh", "-c", "ps -eo pid,comm --no-headers 2>/dev/null || ps -eo pid,comm"],
                    demux=False,
                )
                out = res.output.decode("utf-8", errors="replace") if isinstance(res.output, bytes) else (res.output or "")
                current_pids = set()
                for line in out.splitlines():
                    parts = line.strip().split(None, 1)
                    if len(parts) == 2 and parts[0].isdigit():
                        current_pids.add((parts[0], parts[1]))
                new_pids = current_pids - baseline_pids
                # Only flag if new process is in suspicious set
                for _pid, comm in new_pids:
                    # comm may have leading/trailing whitespace or be "[kthread]" form
                    base_comm = comm.strip().lstrip("[").rstrip("]")
                    if base_comm in _SUSPICIOUS_PROCESS_NAMES:
                        return True

            # If we used baseline path and got nothing, return False
            # (don't fall back to heuristic when baseline IS available)
            if baseline_marker or baseline_pids is not None:
                return False

            # ───────── Path 2: heuristic fallback (no baseline) ─────────
            cmd = (
                "test -f /tmp/exploit.txt -o -f /tmp/ctf_flag.txt "
                "-o -f /tmp/secret_flag.txt && echo HIT || echo MISS"
            )
            result = container.exec_run(cmd, demux=False)
            output = result.output
            if isinstance(output, bytes):
                output = output.decode("utf-8", errors="replace")
            return "HIT" in output
        except Exception:
            return False

    return probe


def compute_progress_or_zero(
    case_id: str,
    trajectory: List[Dict[str, Any]],
    side_effect_probe: Optional[Callable[[], bool]] = None,
    yaml_path: Optional[str] = None,
    log_prefix: str = "[ProgressFallback]",
) -> float:
    """
    Convenience wrapper: dispatch progress for a case, return float (0.0 fallback).

    Args:
        case_id: Vulhub case identifier (e.g., "aj-report/CNVD-2024-15077")
        trajectory: agent's action/observation sequence
        side_effect_probe: optional callable for T3/T4 side-effect detection
        yaml_path: optional override for case_to_signature.yaml location
        log_prefix: prefix for log lines (so caller can identify itself)

    Returns:
        Progress score (0.0 if dispatcher unavailable, case unknown,
        mechanism not implemented, or any error).
    """
    dispatcher = get_dispatcher(yaml_path)
    if dispatcher is None:
        return 0.0

    try:
        score, debug = dispatcher.compute(case_id, trajectory, side_effect_probe=side_effect_probe)
    except Exception as e:
        print(f"{log_prefix} dispatcher error for case={case_id!r}: {e}")
        return 0.0

    if score is None:
        # Either case_not_found, not_implemented, or unknown_mechanism
        status = debug.get("status", "unknown")
        print(f"{log_prefix} case={case_id} status={status}; falling back to 0.0")
        return 0.0

    tier = debug.get("tier_reached", "?")
    mech = debug.get("mechanism", "?")
    print(f"{log_prefix} case={case_id} mechanism={mech} tier={tier} score={score}")
    return float(score)
