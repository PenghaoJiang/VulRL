#!/usr/bin/env python3
"""
Concatenate multiple Parquet files with the same column schema (pandas.concat).

Typical use: merge vulhub training parquet with CTF docker parquet for a single training file.

Usage:
  python dataset/concat_parquets.py \\
    --inputs dataset/train_v4.parquet dataset/train_ctf_docker.parquet \\
    --output dataset/train_combined.parquet

  python dataset/concat_parquets.py -i a.parquet b.parquet c.parquet -o out.parquet
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List

import pandas as pd


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-i",
        "--inputs",
        nargs="+",
        required=True,
        type=Path,
        help="Input .parquet files (order preserved)",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        required=True,
        help="Output .parquet path",
    )
    parser.add_argument(
        "--axis",
        type=int,
        default=0,
        help="concat axis (default: 0 = stack rows)",
    )
    parser.add_argument(
        "--no-ignore-index",
        action="store_true",
        help="If set, preserve original row indices (default: ignore_index=True)",
    )
    args = parser.parse_args()

    paths: List[Path] = [p.resolve() for p in args.inputs]
    for p in paths:
        if not p.is_file():
            print(f"error: not a file: {p}", file=sys.stderr)
            return 1

    dfs = [pd.read_parquet(p) for p in paths]
    cols0 = list(dfs[0].columns)
    for i, df in enumerate(dfs[1:], start=1):
        if list(df.columns) != cols0:
            print(
                f"error: column mismatch vs first file\n"
                f"  first ({paths[0].name}): {cols0}\n"
                f"  [{i}] ({paths[i].name}): {list(df.columns)}",
                file=sys.stderr,
            )
            return 1

    out = pd.concat(
        dfs,
        axis=args.axis,
        ignore_index=not args.no_ignore_index,
    )
    out_path = args.output.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out.to_parquet(out_path, index=False)

    print(f"Concatenated {len(paths)} files -> {out_path}")
    print(f"Rows: {len(out)}  Columns: {list(out.columns)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
