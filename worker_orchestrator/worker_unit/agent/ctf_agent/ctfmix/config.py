"""Config helpers used by the CTFMix runtime and agent stack."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


def _load_dotenv_file(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return
    for raw_line in dotenv_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def find_repo_root() -> Path:
    """
    Find repository root (worker_orchestrator).
    
    For VulRL worker_unit, we're in a different structure than original CTFMix.
    """
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "worker_unit").exists() and (parent / "worker_router").exists():
            return parent
    # Fallback: return worker_orchestrator root
    return Path(__file__).resolve().parent.parent.parent.parent


def find_vulrl_repo_root() -> Path:
    """
    Find VulRL repo root.
    
    NOTE: In worker_unit, we don't have access to the full VulRL structure.
    Return worker_orchestrator root instead.
    """
    return find_repo_root()


def find_workspace_root() -> Path:
    return find_repo_root()


def find_ctfmix_root() -> Path:
    """
    Find ctfmix config root.
    
    In worker_unit, configs are stored in agent/config/, not benchmark/ctfmix/config/.
    __file__ is in: agent/ctf_agent/ctfmix/config.py
    We need to go up to: agent/config/
    """
    # From agent/ctf_agent/ctfmix/ go up to agent/ then into config/
    return Path(__file__).resolve().parent.parent.parent / "config"


def find_ctfmix_config_root() -> Path:
    """
    Find ctfmix config directory.
    
    Returns the same as find_ctfmix_root() since in worker_unit,
    configs are directly in agent/config/ (no nested config/ subdirectory).
    """
    # In original: benchmark/ctfmix/config/
    # In worker_unit: agent/config/ (already pointing to config dir)
    return find_ctfmix_root()


def find_ctfmix_models_config_path() -> Path:
    """Find models_config.yaml"""
    return find_ctfmix_config_root() / "models_config.yaml"


def find_ctfmix_benchmark_root() -> Path:
    return find_ctfmix_root()


def find_enigma_root() -> Path:
    """Backward-compatible alias kept for older enigma-derived call sites."""
    return find_ctfmix_root()


def convert_path_to_abspath(path: Path | str, base_dir: Path | None = None) -> Path:
    path = Path(path)
    default_root = find_ctfmix_root()
    root = base_dir or Path(os.environ.get("SWE_AGENT_CONFIG_ROOT", default_root))
    if not path.is_absolute():
        path = root / path
    resolved = path.resolve()
    if resolved.exists():
        return resolved
    underscored = resolved.with_name(f"_{resolved.name}")
    if underscored.exists():
        return underscored
    return resolved


def convert_paths_to_abspath(paths: list[Path | str], base_dir: Path | None = None) -> list[Path]:
    return [convert_path_to_abspath(path, base_dir=base_dir) for path in paths]


class Config:
    def get(self, key: str, default: Any = None, choices: list[Any] | None = None) -> Any:
        value = os.environ.get(key, default)
        if choices is not None and value not in choices:
            raise ValueError(f"Value {value} for key {key} not in {choices}")
        return value

    def __getitem__(self, key: str) -> Any:
        if key not in os.environ:
            raise KeyError(f"Key {key} not found in environment variables")
        return os.environ[key]

    def __contains__(self, key: str) -> bool:
        return key in os.environ


# Load .env if it exists (optional for worker_unit)
try:
    _load_dotenv_file(find_repo_root() / ".env")
except:
    pass  # .env not required

keys_config = Config()
