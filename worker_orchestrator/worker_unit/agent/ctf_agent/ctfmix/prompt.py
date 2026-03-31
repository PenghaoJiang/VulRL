"""Prompt loading from the repo-local benchmark/ctfmix config bundle."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .agents import AgentConfig
from .config import find_ctfmix_config_root


def get_default_prompt_config_path() -> Path:
    return find_ctfmix_config_root() / "default_ctf.yaml"


def load_default_agent_config(config_path: str | Path | None = None) -> AgentConfig:
    return AgentConfig.load_yaml(config_path or get_default_prompt_config_path())


def _build_prompt_values(agent_config: AgentConfig, task: dict[str, Any], state: dict[str, str]) -> dict[str, Any]:
    values = {
        "flag_format": task.get("flag_format", "flag{...}"),
        "category_friendly": task.get("category_friendly", task.get("category", "misc")),
        "name": task.get("name", task.get("task_id", "unknown")),
        "points": task.get("points", "unknown"),
        "description": task.get("description", ""),
        "files": ", ".join(task.get("files", [])) or "none",
        "server_description": task.get("server_description", ""),
        "open_file": state.get("open_file", "n/a"),
        "working_dir": state.get("working_dir", "."),
        "interactive_session": state.get("interactive_session", "n/a"),
        "command_docs": agent_config.command_docs or "",
        **agent_config.env_variables,
    }
    return values


def build_initial_messages(
    agent_config: AgentConfig,
    task: dict[str, Any],
    state: dict[str, str],
) -> list[dict[str, str]]:
    values = _build_prompt_values(agent_config, task, state)
    return [
        {"role": "system", "content": agent_config.system_template.format(**values)},
        {"role": "user", "content": agent_config.instance_template.format(**values)},
    ]


def build_instance_prompt(agent_config: AgentConfig, task: dict[str, Any], state: dict[str, str]) -> str:
    messages = build_initial_messages(agent_config, task, state)
    return "\n\n".join(message["content"] for message in messages)
