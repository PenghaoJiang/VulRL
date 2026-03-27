"""Standalone entrypoint for CTFMix runtime without SkyRL/Ray."""

from __future__ import annotations

import sys
from pathlib import Path


def _ensure_vulrl_path() -> None:
    current = Path(__file__).resolve()
    repo_root = current.parent.parent
    vulrl_root = current.parent.parent / "SkyRL" / "skyrl-train" / "vulrl_inside_skyrl"
    for path in [repo_root, vulrl_root]:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))


def main() -> int:
    _ensure_vulrl_path()
    from vulrl.ctfmix.standalone import main as standalone_main

    return standalone_main()


if __name__ == "__main__":
    raise SystemExit(main())
