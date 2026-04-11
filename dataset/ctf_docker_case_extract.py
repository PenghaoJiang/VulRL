#!/usr/bin/env python3
"""
Scan benchmark/ctfmix for NYU and Cybench challenges that ship docker-compose.yml.

Writes two line lists (paths relative to ctfmix root, POSIX slashes):
  - ctf_docker_nyu_cases.txt
  - ctf_docker_cybench_cases.txt

Cybench paths in CybenchDockerAdapter.CYBENCH_SKIP_REL_PATHS are omitted by default
(shared_net / non-ctfnet auxiliary bundles the worker adapter skips).

Usage:
  python ctf_docker_case_extract.py
  python ctf_docker_case_extract.py --ctfmix-root /path/to/ctfmix --out-dir ./dataset
  python ctf_docker_case_extract.py --include-skipped
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import FrozenSet, List, Set

_REPO_ROOT = Path(__file__).resolve().parent.parent
_WORKER_ORCH = _REPO_ROOT / "worker_orchestrator"
sys.path.insert(0, str(_WORKER_ORCH))
try:
    from worker_unit.adapters.cybench_docker_adapter import CYBENCH_SKIP_REL_PATHS
except ImportError:
    CYBENCH_SKIP_REL_PATHS = frozenset(
        {
            "cybench/S23/pwn/network-tools/challenge",
            "cybench/HKC/web/05-motp/public",
        }
    )


def _posix_rel(ctfmix_root: Path, compose_file: Path) -> str:
    rel = compose_file.parent.resolve().relative_to(ctfmix_root.resolve())
    return rel.as_posix()


def _collect_under(
    ctfmix_root: Path,
    subdir: str,
    skip_paths: FrozenSet[str],
    include_skipped: bool,
) -> List[str]:
    base = ctfmix_root / subdir
    if not base.is_dir():
        return []
    found: Set[str] = set()
    for compose in base.rglob("docker-compose.yml"):
        if not compose.is_file():
            continue
        rel = _posix_rel(ctfmix_root, compose)
        if (
            not include_skipped
            and subdir == "cybench"
            and rel in skip_paths
        ):
            continue
        found.add(rel)
    return sorted(found)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ctfmix-root",
        type=Path,
        default=_REPO_ROOT / "benchmark" / "ctfmix",
        help="ctfmix root (contains nyu_ctf/ and cybench/)",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent,
        help="Directory for output .txt files",
    )
    parser.add_argument(
        "--include-skipped",
        action="store_true",
        help="Include Cybench paths the Docker adapter normally skips",
    )
    args = parser.parse_args()

    ctfmix_root = args.ctfmix_root.resolve()
    if not ctfmix_root.is_dir():
        print(f"error: ctfmix root not found: {ctfmix_root}", file=sys.stderr)
        return 1

    skip: FrozenSet[str] = CYBENCH_SKIP_REL_PATHS
    nyu = _collect_under(ctfmix_root, "nyu_ctf", skip, args.include_skipped)
    cyb = _collect_under(ctfmix_root, "cybench", skip, args.include_skipped)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    nyu_out = args.out_dir / "ctf_docker_nyu_cases.txt"
    cyb_out = args.out_dir / "ctf_docker_cybench_cases.txt"

    nyu_out.write_text("\n".join(nyu) + ("\n" if nyu else ""), encoding="utf-8")
    cyb_out.write_text("\n".join(cyb) + ("\n" if cyb else ""), encoding="utf-8")

    print(f"ctfmix_root={ctfmix_root}")
    print(f"NYU cases (docker-compose.yml): {len(nyu)} -> {nyu_out}")
    print(f"Cybench cases: {len(cyb)} -> {cyb_out}")
    if not args.include_skipped and skip:
        print(f"Cybench skipped by adapter (omitted): {sorted(skip)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
