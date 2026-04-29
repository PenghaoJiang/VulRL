"""
Vulhub Read-based reward for SQLi, LFI, and other data exfiltration challenges.

Outcome (1.0): exact flag string found in any observation.
Progress fallback ([0.0, 0.20]): if outcome failed, route through
ProgressDispatcher (v2.3 taxonomy) to give a process reward — this is what
makes GRPO group variance non-zero on partial-progress trajectories.
"""

from typing import List, Dict, Any, Optional

from worker_unit.reward.task_specific.vulhub_progress_helper import (
    compute_progress_or_zero,
)


class VulhubReadReward:
    """
    Flag-grep + progress-fallback reward for Vulhub Read-based challenges.

    Reward:
        - 1.0 if exact oracle_flag found in any trajectory observation
        - progress score [0.0, 0.20] otherwise (computed by ProgressDispatcher)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize VulhubReadReward.

        Args:
            config: Reward configuration. Expected keys:
                - oracle_flag: random flag string to search for
                - vulhub_path: case identifier matching case_to_signature.yaml
                - case_dir: optional path to case directory (logging only)
                - enable_progress_fallback: bool (default True)
        """
        self.config = config or {}
        self.oracle_flag = self.config.get("oracle_flag")
        # vulhub_path doubles as case_id (matches yaml key)
        self.case_id = self.config.get("vulhub_path", "")
        self.case_dir = self.config.get("case_dir")
        self.enable_progress_fallback = self.config.get("enable_progress_fallback", True)

        flag_status = "[SET]" if self.oracle_flag else "[NOT SET]"
        print(f"[VulhubReadReward] Initialized case_id={self.case_id!r} "
              f"flag={flag_status} progress_fallback={self.enable_progress_fallback}")
        if self.case_dir:
            print(f"[VulhubReadReward] Case directory: {self.case_dir}")

    def compute(self, trajectory: List[Dict[str, Any]], task_id: str) -> float:
        """
        Compute reward by flag-search, with progress-fallback on miss.

        Returns:
            1.0 if exact flag found in any observation,
            else progress score in [0.0, 0.20] (when progress_fallback enabled),
            else 0.0
        """
        # ───────────── outcome stage ─────────────
        outcome_passed = self._search_flag(trajectory, task_id)
        if outcome_passed:
            print(f"[VulhubReadReward] task={task_id} reward=1.0 (flag found)")
            return 1.0

        # ───────────── progress fallback ─────────────
        if not self.enable_progress_fallback:
            print(f"[VulhubReadReward] task={task_id} reward=0.0 "
                  f"(flag not found; progress_fallback disabled)")
            return 0.0

        if not self.case_id:
            print(f"[VulhubReadReward] task={task_id} reward=0.0 "
                  f"(flag not found; no case_id for progress lookup)")
            return 0.0

        # Read-based cases don't have a meaningful side-effect probe (no /tmp/exploit.txt
        # — successful exploit just leaks data through observations). Pass None.
        progress_score = compute_progress_or_zero(
            case_id=self.case_id,
            trajectory=trajectory,
            side_effect_probe=None,
            log_prefix=f"[VulhubReadReward:progress task={task_id}]",
        )
        print(f"[VulhubReadReward] task={task_id} reward={progress_score} "
              f"(flag not found; progress fallback)")
        return progress_score

    # ─────────────────────────────────────────────────────────────
    # Private: flag search (extracted from old compute())
    # ─────────────────────────────────────────────────────────────

    def _search_flag(self, trajectory: List[Dict[str, Any]], task_id: str) -> bool:
        """Search for exact oracle_flag in any observation. Return True if found."""
        if not self.oracle_flag:
            print(f"[VulhubReadReward] task={task_id} ERROR: no oracle_flag in config")
            return False

        if not trajectory:
            print(f"[VulhubReadReward] task={task_id} empty trajectory")
            return False

        print(f"[VulhubReadReward] task={task_id} checking "
              f"{len(trajectory)} steps for flag={self.oracle_flag}")

        for idx, step in enumerate(trajectory):
            observation = step.get("observation", "")
            if not isinstance(observation, str):
                observation = str(observation)

            if self.oracle_flag in observation:
                # Log context for debugging
                flag_pos = observation.find(self.oracle_flag)
                start = max(0, flag_pos - 50)
                end = min(len(observation), flag_pos + len(self.oracle_flag) + 50)
                print(f"[VulhubReadReward] ✓ FLAG FOUND in step {idx+1}; "
                      f"context: ...{observation[start:end]}...")
                return True

        # Log first 100 chars of each observation for debug visibility
        print(f"[VulhubReadReward] task={task_id} ✗ flag not found; obs samples:")
        for idx, step in enumerate(trajectory[:5]):
            obs = str(step.get("observation", ""))[:100]
            print(f"  Step {idx+1}: {obs}...")
        return False
