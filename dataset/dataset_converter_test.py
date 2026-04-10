#!/usr/bin/env python3
"""
Smoke-test parquet: exactly **3 rows** — first vulhub-style sample, first NYU CTF, first Cybench.

1. **Vulhub**: Picks the lexicographically first `benchmark/vulhub/**/docker-compose.yml` scenario,
   materializes a tiny temporary “result folder” (metadata.json + minimal poc/verify + README copied
   from that scenario) and reuses `ResultFolderConverter._convert_folder` from dataset_converter_v2.

2. **NYU / Cybench**: First non-empty line from the same list files as `dataset_converter_ctf.py`,
   reusing `_convert_one` from `dataset_converter_ctf`.

Output schema matches `dataset_converter_v2.py` / `dataset_converter_ctf.py` (same columns).

Usage:
  python dataset/dataset_converter_test.py --output dataset/train_smoke_3way.parquet
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd

_DATASET_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _DATASET_DIR.parent
sys.path.insert(0, str(_DATASET_DIR))

from dataset_converter_v2 import ResultFolderConverter  # noqa: E402
from dataset_converter_v2 import SKYRL_TOOL_DEFINITIONS  # noqa: E402
from dataset_converter_ctf import (  # noqa: E402
    _convert_one,
    _read_lines,
)

_COLS: List[str] = [
    "prompt",
    "env_class",
    "env_config",
    "poc_info",
    "tools",
    "task_id",
    "metadata",
    "vulhub_path",
    "cve_id",
]

_DEFAULT_VULHUB = _REPO_ROOT / "benchmark" / "vulhub"
_DEFAULT_CTFMIX = _REPO_ROOT / "benchmark" / "ctfmix"


def _first_vulhub_scenario(vulhub_base: Path) -> Tuple[str, Path]:
    """Return (relative vulhub_path, scenario_dir) for first compose scenario by path sort."""
    pairs: List[Tuple[str, Path]] = []
    for compose in vulhub_base.rglob("docker-compose.yml"):
        if not compose.is_file():
            continue
        rel = compose.parent.resolve().relative_to(vulhub_base.resolve()).as_posix()
        pairs.append((rel, compose.parent.resolve()))
    if not pairs:
        raise FileNotFoundError(f"No docker-compose.yml under {vulhub_base}")
    pairs.sort(key=lambda x: x[0])
    return pairs[0]


def _build_vulhub_row_via_temp_result(
    vulhub_base: Path,
) -> Dict[str, str]:
    rel, scenario_dir = _first_vulhub_scenario(vulhub_base)
    tools_json = json.dumps(SKYRL_TOOL_DEFINITIONS, ensure_ascii=False)
    conv = ResultFolderConverter(vulhub_base_dir=str(vulhub_base.resolve()))

    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp) / "vulhub_smoke_sample"
        folder.mkdir(parents=True)
        (folder / "metadata.json").write_text(
            json.dumps({"vulhub_path": rel, "folder_name": folder.name}, indent=2),
            encoding="utf-8",
        )
        (folder / "poc.py").write_text(
            "# Smoke sample for dataset_converter_test.py\n"
            "import argparse\n"
            "p = argparse.ArgumentParser()\n"
            'p.add_argument("--port", type=int, default=80)\n'
            "args = p.parse_args()\n",
            encoding="utf-8",
        )
        (folder / "verify.py").write_text("", encoding="utf-8")
        readme = scenario_dir / "README.md"
        if readme.is_file():
            shutil.copyfile(readme, folder / "README.md")
        else:
            alt = scenario_dir / "README.zh-cn.md"
            if alt.is_file():
                shutil.copyfile(alt, folder / "README.md")
            else:
                (folder / "README.md").write_text(
                    f"# {rel}\n\n(Synthetic README for smoke parquet.)\n",
                    encoding="utf-8",
                )

        row = conv._convert_folder(folder, tools_json)
    print(f"vulhub (first scenario): {rel}")
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=_DATASET_DIR / "train_smoke_3way.parquet",
        help="Output parquet path (default: dataset/train_smoke_3way.parquet)",
    )
    parser.add_argument(
        "--vulhub-base",
        type=Path,
        default=_DEFAULT_VULHUB,
        help="Vulhub benchmark root",
    )
    parser.add_argument(
        "--ctfmix-root",
        type=Path,
        default=_DEFAULT_CTFMIX,
        help="ctfmix root",
    )
    parser.add_argument(
        "--nyu-list",
        type=Path,
        default=_DATASET_DIR / "ctf_docker_nyu_cases.txt",
    )
    parser.add_argument(
        "--cybench-list",
        type=Path,
        default=_DATASET_DIR / "ctf_docker_cybench_cases.txt",
    )
    parser.add_argument("--max-steps", type=int, default=30)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    vulhub_base = args.vulhub_base.resolve()
    ctfmix_root = args.ctfmix_root.resolve()

    rows: List[Dict[str, str]] = []

    rows.append(_build_vulhub_row_via_temp_result(vulhub_base))

    tools_json = json.dumps(SKYRL_TOOL_DEFINITIONS, ensure_ascii=False)
    seen: Dict[str, str] = {}

    nyu_lines = _read_lines(args.nyu_list) if args.nyu_list.is_file() else []
    cyb_lines = _read_lines(args.cybench_list) if args.cybench_list.is_file() else []
    if not nyu_lines:
        raise FileNotFoundError(
            f"NYU list missing or empty: {args.nyu_list} (run ctf_docker_case_extract.py)"
        )
    if not cyb_lines:
        raise FileNotFoundError(
            f"Cybench list missing or empty: {args.cybench_list} (run ctf_docker_case_extract.py)"
        )

    rows.append(
        _convert_one(
            nyu_lines[0],
            "nyu_ctf",
            ctfmix_root,
            args.max_steps,
            args.timeout,
            tools_json,
            seen,
        )
    )
    print(f"nyu_ctf (first list line): {nyu_lines[0]}")

    rows.append(
        _convert_one(
            cyb_lines[0],
            "cybench_docker",
            ctfmix_root,
            args.max_steps,
            args.timeout,
            tools_json,
            seen,
        )
    )
    print(f"cybench_docker (first list line): {cyb_lines[0]}")

    df = pd.DataFrame(rows, columns=_COLS)
    out = args.output.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out, index=False)
    print(f"Wrote 3 rows -> {out}")
    print(f"task_id column: {list(df['task_id'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
