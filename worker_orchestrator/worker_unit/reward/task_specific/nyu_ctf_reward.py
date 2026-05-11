"""NYU CTF (ctfmix) binary flag reward from trajectory."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .ctf_flag_shared import (
    compute_binary_flag_reward,
    compute_subtask_bonus_from_trajectory,
    get_ctf_subtasks_from_config,
)


class NYUCTFFlagReward:
    """1.0 if trajectory matches challenge flag; 0.0 if unsupported or wrong."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def compute(self, trajectory: List[Dict[str, Any]], task_id: str) -> float:
        expected = self.config.get("expected_flag")
        supported = self.config.get("ctfmix_supported", True)
        fmt = self.config.get("flag_format", "flag{...}")
        base_reward = compute_binary_flag_reward(
            trajectory,
            expected,
            ctfmix_supported=bool(supported),
            flag_format=str(fmt),
        )
        subtasks = get_ctf_subtasks_from_config(self.config)
        per_subtask_reward = float(self.config.get("subtask_reward_weight", 0.1))
        subtask_bonus, correct_indices = compute_subtask_bonus_from_trajectory(
            trajectory,
            subtasks,
            expected_flag=expected,
            per_subtask_reward=per_subtask_reward,
            log_prefix="NYUCTFFlagReward",
        )
        total_reward = base_reward + subtask_bonus
        print(
            "[NYUCTFFlagReward] "
            f"task={task_id} base_reward={base_reward} subtask_bonus={subtask_bonus} "
            f"correct_subtasks={correct_indices} total_reward={total_reward} "
            f"supported={supported}"
        )
        return total_reward
