"""
Progress Dispatcher: routes (case_id, trajectory) to the right progress function.

Loads case_to_signature.yaml at init and dispatches based on `primary` mechanism.

Currently implements 3 of 12 mechanisms (M03/M05/M10 = 39/67 cases).
Other mechanisms return (None, {"status": "not_implemented"}) — caller should
fall back to outcome-only reward or generic fallback.

Usage:
    from worker_unit.reward.progress import ProgressDispatcher

    dispatcher = ProgressDispatcher("vulhub_oracle_and_test/case_to_signature.yaml")
    score, debug = dispatcher.compute(
        case_id="struts2/s2-045",
        trajectory=trajectory_list,
        side_effect_probe=lambda: adapter.has_new_files(),
    )
"""

import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .m01_sql_injection import compute_m01_progress
from .m03_path_traversal import compute_m03_progress
from .m04_xxe import compute_m04_progress
from .m05_engine_injection import compute_m05_progress
from .m06_cmd_injection import compute_m06_progress
from .m07_deserialization import compute_m07_progress
from .m08_upload_then_access import compute_m08_progress
from .m09_auth_bypass_chain import compute_m09_progress
from .m10_config_abuse import compute_m10_progress
from .m11_non_http_protocol import compute_m11_progress
from .utils import split_actions_observations


# Mechanisms with implementations (all except deferred M02-nosql-injection)
IMPLEMENTED_MECHANISMS = {
    "M01-sql-injection",
    "M03-path-traversal",
    "M04-xxe",
    "M05-engine-injection",
    "M06-cmd-injection",
    "M07-deserialization",
    "M08-upload-then-access",
    "M09-auth-bypass-chain",
    "M10-config-abuse",
    "M11-non-http-protocol",
}


def _compute_misc_lite(trajectory: List[Dict[str, Any]]) -> Tuple[float, Dict[str, Any]]:
    """
    M12 misc-lite fallback: very weak interaction signal.
    T1 (0.02): agent had at least one non-empty observation
    T2 (0.04): T1 + multi-step state-aware behavior (later step references earlier output)
    """
    actions, observations = split_actions_observations(trajectory)

    has_nonempty_obs = any(obs.strip() for obs in observations)
    t1_hit = has_nonempty_obs

    # Multi-step state awareness: a later action contains a substring from an earlier obs
    multi_step_state = False
    if len(trajectory) >= 2:
        for i, obs in enumerate(observations[:-1]):
            obs_words = re.findall(r"\b[A-Za-z0-9_]{6,}\b", obs)
            for word in obs_words:
                # Check if any later action contains this word
                for later_action in actions[i + 1:]:
                    if word in later_action:
                        multi_step_state = True
                        break
                if multi_step_state:
                    break
            if multi_step_state:
                break
    t2_hit = t1_hit and multi_step_state

    if t2_hit:
        score = 0.04
        tier = "T2"
    elif t1_hit:
        score = 0.02
        tier = "T1"
    else:
        score = 0.0
        tier = "T0"

    return score, {
        "mechanism": "M12-misc-lite",
        "tier_reached": tier,
        "score": score,
        "t1_hit": t1_hit,
        "t2_hit": t2_hit,
    }


class ProgressDispatcher:
    """Routes per-case progress reward computation to the right mechanism."""

    def __init__(self, signature_yaml_path: str | Path):
        self.yaml_path = Path(signature_yaml_path)
        self._cases: Dict[str, Dict[str, Any]] = {}
        self._load_yaml()

    def _load_yaml(self) -> None:
        """
        Parse case_to_signature.yaml. We use a minimal hand-parser to avoid
        adding pyyaml as a dependency to the worker_unit module.

        The yaml structure is flat:
            "case_id":
              outcome: rce
              primary: M05-engine-injection
              subtype: template
              secondary: in-url-param
              ...
        """
        text = self.yaml_path.read_text()
        current_case = None
        current_data: Dict[str, Any] = {}

        for raw_line in text.splitlines():
            # Strip comments and trailing whitespace, but keep leading whitespace
            line = raw_line.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            # Top-level key: "case_id":
            m = re.match(r'^"([^"]+)":\s*$', line)
            if m:
                if current_case is not None:
                    self._cases[current_case] = current_data
                current_case = m.group(1)
                current_data = {}
                continue
            # Indented key: value
            if current_case and re.match(r"^\s+\w", line):
                key_match = re.match(r"^\s+(\w+):\s*(.*)$", line)
                if key_match:
                    k = key_match.group(1)
                    v = key_match.group(2).strip()
                    # Strip quotes
                    if v.startswith('"') and v.endswith('"'):
                        v = v[1:-1]
                    if v == "null":
                        v = None
                    elif v in ("true", "false"):
                        v = v == "true"
                    current_data[k] = v

        # Persist final case
        if current_case is not None:
            self._cases[current_case] = current_data

    @property
    def case_count(self) -> int:
        return len(self._cases)

    def get_case_meta(self, case_id: str) -> Optional[Dict[str, Any]]:
        """Return parsed metadata for a case, or None if not found."""
        return self._cases.get(case_id)

    def compute(
        self,
        case_id: str,
        trajectory: List[Dict[str, Any]],
        side_effect_probe: Optional[Callable[[], bool]] = None,
    ) -> Tuple[Optional[float], Dict[str, Any]]:
        """
        Dispatch to the right progress function for case_id.

        Returns (score, debug_info).

        Special return values:
          - score=None, debug={"status": "not_implemented"}:
              case maps to a mechanism that doesn't have a progress function yet.
              Caller should use fallback (outcome-only or weak generic).
          - score=None, debug={"status": "case_not_found"}:
              case_id not in yaml. Caller may fall back to misc-lite.
        """
        meta = self.get_case_meta(case_id)
        if meta is None:
            return None, {
                "status": "case_not_found",
                "case_id": case_id,
                "available_count": self.case_count,
            }

        primary = meta.get("primary", "")

        # Outcome gating: caller should call this only when oracle_test failed.
        # We always compute progress; caller decides whether to override with 1.0.

        if primary == "M01-sql-injection":
            score, debug = compute_m01_progress(trajectory)
        elif primary == "M03-path-traversal":
            score, debug = compute_m03_progress(trajectory)
        elif primary == "M04-xxe":
            score, debug = compute_m04_progress(trajectory)
        elif primary == "M05-engine-injection":
            score, debug = compute_m05_progress(
                trajectory,
                subtype=meta.get("subtype"),
                side_effect_probe=side_effect_probe,
            )
        elif primary == "M10-config-abuse":
            score, debug = compute_m10_progress(
                trajectory,
                side_effect_probe=side_effect_probe,
            )
        elif primary == "M06-cmd-injection":
            score, debug = compute_m06_progress(
                trajectory,
                side_effect_probe=side_effect_probe,
            )
        elif primary == "M07-deserialization":
            score, debug = compute_m07_progress(
                trajectory,
                side_effect_probe=side_effect_probe,
            )
        elif primary == "M08-upload-then-access":
            score, debug = compute_m08_progress(trajectory)
        elif primary == "M09-auth-bypass-chain":
            score, debug = compute_m09_progress(trajectory)
        elif primary == "M11-non-http-protocol":
            score, debug = compute_m11_progress(trajectory)
        elif primary == "M12-misc-lite":
            score, debug = _compute_misc_lite(trajectory)
        elif primary in {
            "M02-nosql-injection",   # deferred — no current cases
        }:
            return None, {
                "status": "not_implemented",
                "mechanism": primary,
                "case_id": case_id,
                "note": "mechanism scheduled for Step 4 (extension to remaining 8)",
            }
        else:
            return None, {
                "status": "unknown_mechanism",
                "mechanism": primary,
                "case_id": case_id,
            }

        # Annotate debug with case metadata
        debug["case_id"] = case_id
        debug["outcome_type"] = meta.get("outcome")
        debug["secondary_carrier"] = meta.get("secondary")
        return score, debug
