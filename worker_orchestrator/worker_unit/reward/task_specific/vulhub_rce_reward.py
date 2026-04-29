"""
Vulhub RCE-specific reward using oracle_test.sh verification.

Executes oracle_test.sh on the host after trajectory completion to verify
if the exploit succeeded. Returns 1.0 if test passes (exit code 0).

If oracle_test FAILS, falls back to ProgressDispatcher (v2.3 taxonomy)
to compute a process reward in [0.0, 0.20] — this is what makes GRPO
group variance non-zero even when the oracle hasn't fully passed yet.

Outcome gating preserved:
    return 1.0 if oracle_test passes
    return progress_score in [0.0, 0.20] otherwise (was: 0.0)
"""

import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

from worker_unit.reward.task_specific.vulhub_progress_helper import (
    compute_progress_or_zero,
    make_side_effect_probe,
)


class VulhubRCEReward:
    """
    Oracle test + progress-fallback reward for Vulhub RCE challenges.

    Reward:
        - 1.0 if oracle_test.sh exits with code 0 (exploit succeeded)
        - progress score [0.0, 0.20] otherwise (computed by ProgressDispatcher)
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize VulhubRCEReward.

        Args:
            config: Environment configuration. Expected keys:
                - adapter: VulhubAdapter instance (for container info)
                - vulhub_base_path: Base path to vulhub benchmark
                - vulhub_path: Relative path to the specific case (also used as case_id)
                - case_dir: Absolute path to case directory (optional)
                - enable_progress_fallback: bool (default True) — turn off to revert
                  to legacy 0.0 behavior on outcome failure
        """
        self.config = config or {}
        self.adapter = self.config.get("adapter")
        # vulhub_path doubles as case_id (matches yaml key)
        self.case_id = self.config.get("vulhub_path", "")
        self.enable_progress_fallback = self.config.get("enable_progress_fallback", True)

        # Resolve case directory
        vulhub_base_path = self.config.get("vulhub_base_path", "")
        case_dir = self.config.get("case_dir")

        if case_dir:
            self.case_dir = Path(case_dir)
        elif vulhub_base_path and self.case_id:
            self.case_dir = Path(vulhub_base_path) / self.case_id
        else:
            self.case_dir = None

        print(f"[VulhubRCEReward] Initialized case_id={self.case_id!r} "
              f"progress_fallback={self.enable_progress_fallback}")

    def compute(self, trajectory: List[Dict[str, Any]], task_id: str) -> float:
        """
        Compute reward by running oracle_test.sh, with progress-fallback.

        Args:
            trajectory: list of {action, observation} steps
            task_id: vulhub task ID for logging (e.g., "aj-report/CNVD-2024-15077_<ts>")

        Returns:
            1.0 if oracle_test.sh passes,
            else progress score in [0.0, 0.20] (when progress_fallback enabled),
            else 0.0
        """
        # ───────────── outcome stage ─────────────
        outcome_passed = self._run_oracle_test(task_id)
        if outcome_passed:
            print(f"[VulhubRCEReward] task={task_id} reward=1.0 (oracle_test PASSED)")
            return 1.0

        # ───────────── progress fallback ─────────────
        if not self.enable_progress_fallback:
            print(f"[VulhubRCEReward] task={task_id} reward=0.0 "
                  f"(oracle_test FAILED; progress_fallback disabled)")
            return 0.0

        if not self.case_id:
            print(f"[VulhubRCEReward] task={task_id} reward=0.0 "
                  f"(oracle_test FAILED; no case_id for progress lookup)")
            return 0.0

        # Build side-effect probe from adapter (heuristic, no baseline yet)
        probe = make_side_effect_probe(self.adapter)
        progress_score = compute_progress_or_zero(
            case_id=self.case_id,
            trajectory=trajectory,
            side_effect_probe=probe,
            log_prefix=f"[VulhubRCEReward:progress task={task_id}]",
        )
        print(f"[VulhubRCEReward] task={task_id} reward={progress_score} "
              f"(oracle_test FAILED; progress fallback)")
        return progress_score

    # ─────────────────────────────────────────────────────────────
    # Private: oracle_test execution (extracted from old compute())
    # ─────────────────────────────────────────────────────────────

    def _run_oracle_test(self, task_id: str) -> bool:
        """
        Run oracle_test.sh on the host. Return True iff exit code is 0.
        All error/missing-config branches return False.
        """
        if not self.adapter:
            print(f"[VulhubRCEReward] No adapter provided")
            return False

        if not self.case_dir or not self.case_dir.exists():
            print(f"[VulhubRCEReward] Case directory not found: {self.case_dir}")
            return False

        oracle_test_script = self.case_dir / "oracle_test.sh"
        if not oracle_test_script.exists():
            print(f"[VulhubRCEReward] oracle_test.sh not found in {self.case_dir}")
            return False

        print(f"[VulhubRCEReward] Running oracle_test.sh for task={task_id}")

        env_vars = {
            "TARGET_CONTAINER": self.adapter.target_container_name or "",
            "TARGET_CONTAINER_ID": self.adapter.target_container_obj.id
                                    if self.adapter.target_container_obj else "",
            "COMPOSE_PROJECT_NAME": self.adapter.project_name or "",
            "ATTACKER_CONTAINER": self.adapter.attacker_container_name or "",
            "ORACLE_CASE_DIR": str(self.case_dir.resolve()),
        }

        print(f"[VulhubRCEReward] Env: TARGET_CONTAINER={env_vars['TARGET_CONTAINER']}, "
              f"COMPOSE_PROJECT_NAME={env_vars['COMPOSE_PROJECT_NAME']}")

        try:
            result = subprocess.run(
                ["bash", str(oracle_test_script)],
                cwd=str(self.case_dir),
                env={**subprocess.os.environ, **env_vars},
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.stdout:
                print(f"[VulhubRCEReward] oracle_test.sh stdout:\n{result.stdout}")
            if result.stderr:
                print(f"[VulhubRCEReward] oracle_test.sh stderr:\n{result.stderr}")

            return result.returncode == 0

        except subprocess.TimeoutExpired:
            print(f"[VulhubRCEReward] oracle_test.sh timed out")
            return False
        except Exception as e:
            print(f"[VulhubRCEReward] Error running oracle_test.sh: {e}")
            return False
