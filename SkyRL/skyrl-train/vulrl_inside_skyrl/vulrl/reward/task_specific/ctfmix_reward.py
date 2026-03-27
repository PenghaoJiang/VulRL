"""Terminal-only reward for CTFMix tasks."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class CTFMixReward:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    def compute(self, trajectory: List[Dict[str, Any]], task_id: str) -> float:
        # Real reward should come from the adapter/runtime terminal result.
        return 0.0
