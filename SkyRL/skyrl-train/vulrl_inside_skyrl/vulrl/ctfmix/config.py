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
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "vulrl").exists() and (parent / "main_training.py").exists():
            return parent
    raise RuntimeError("Could not find vulrl_inside_skyrl repository root")


def find_vulrl_repo_root() -> Path:
    current = Path(__file__).resolve()
    for parent in [current] + list(current.parents):
        if (parent / "SkyRL").exists() and (parent / "dataset").exists() and (parent / "benchmark").exists():
            return parent
    raise RuntimeError("Could not find inner VulRL repository root")


def find_workspace_root() -> Path:
    return find_vulrl_repo_root()


def find_ctfmix_root() -> Path:
    return find_vulrl_repo_root() / "benchmark" / "ctfmix"


def find_ctfmix_config_root() -> Path:
    return find_ctfmix_root() / "config"


def find_ctfmix_models_config_path() -> Path:
    return find_ctfmix_root() / "models_config.yaml"


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


_load_dotenv_file(find_vulrl_repo_root() / ".env")
keys_config = Config()
