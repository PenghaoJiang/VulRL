"""CTFMix adapter that wraps the standalone EnIGMA-style runtime."""

from __future__ import annotations

from typing import Any, Dict, Tuple

from ..base.env_adapter import BaseEnvAdapter
from ..base.env_types import ActionType, StandardAction
from ...ctfmix.runtime import CTFMixRuntime, RuntimeTask


class CTFMixAdapter(BaseEnvAdapter):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.runtime: CTFMixRuntime | None = None
        self.last_info: Dict[str, Any] = {}

    def setup(self) -> None:
        backend_config = dict(self.config.get("backend_config", {}))
        backend_config.setdefault("task_id", self.config.get("task_id", "ctfmix-task"))
        backend_config.setdefault("name", self.config.get("task_id", "ctfmix-task"))
        backend_config.setdefault("internal_port", self.config.get("target_port", 0))
        backend_config.setdefault("box", self.config.get("target_host", "target"))
        if self.config.get("command_config"):
            backend_config.setdefault("command_config", self.config["command_config"])
        task = RuntimeTask.from_dict(backend_config)
        self.runtime = CTFMixRuntime(task, config_path=task.command_config)
        self.runtime.prepare()

    def teardown(self) -> None:
        if self.runtime is not None:
            self.runtime.close()

    def reset_backend(self) -> str:
        assert self.runtime is not None
        observation, info = self.runtime.reset()
        self.last_info = info
        return observation

    def step_backend(self, action: StandardAction) -> Tuple[str, float, bool, Dict]:
        assert self.runtime is not None
        if action.action_type != ActionType.BASH:
            return "Error: CTFMixAdapter currently only supports bash actions", 0.0, False, {"unsupported": True}
        observation, reward, done, info = self.runtime.step(action.arguments.get("command", ""))
        self.last_info = info
        return observation or "", reward, done, info

    def _get_target_info(self) -> Dict[str, Any]:
        backend = self.config.get("backend_config", {})
        return {
            "host": backend.get("box", self.config.get("target_host", "target")),
            "port": backend.get("internal_port", self.config.get("target_port", 0)),
            "protocol": self.config.get("target_protocol", "tcp"),
        }

    def get_terminal_reward(self) -> float | None:
        if self.runtime is None:
            return None
        return self.runtime.terminal_reward
