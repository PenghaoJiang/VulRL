"""NYU CTF (ctfmix) binary flag reward from trajectory."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .ctf_flag_shared import compute_binary_flag_reward


class NYUCTFFlagReward:
    """1.0 if trajectory matches challenge flag; 0.0 if unsupported or wrong."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def compute(self, trajectory: List[Dict[str, Any]], task_id: str) -> float:
        expected = self.config.get("expected_flag")
        supported = self.config.get("ctfmix_supported", True)
        fmt = self.config.get("flag_format", "flag{...}")
        r = compute_binary_flag_reward(
            trajectory,
            expected,
            ctfmix_supported=bool(supported),
            flag_format=str(fmt),
        )
        print(f"[NYUCTFFlagReward] task={task_id} reward={r} supported={supported}")
        return r
