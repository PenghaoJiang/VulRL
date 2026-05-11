#!/usr/bin/env python3
"""Build benchmark/ctfmix/nyu_ctf_subtask from the reviewed NYU metadata export."""

from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from typing import Dict, List


SCRIPT_PATH = Path(__file__).resolve()
CTFMIX_ROOT = SCRIPT_PATH.parents[1]
VULRL_ROOT = SCRIPT_PATH.parents[3]
HAORAN_ROOT = SCRIPT_PATH.parents[4]

SOURCE_BENCHMARK_ROOT = CTFMIX_ROOT / "nyu_ctf"
TARGET_BENCHMARK_ROOT = CTFMIX_ROOT / "nyu_ctf_subtask"
SOURCE_INDEX_PATH = CTFMIX_ROOT / "nyu_ctf.json"
TARGET_INDEX_PATH = CTFMIX_ROOT / "nyu_ctf_subtask.json"
SOURCE_DOCKER_CASE_LIST = VULRL_ROOT / "dataset" / "ctf_docker_nyu_cases.txt"
TARGET_CASE_LIST = VULRL_ROOT / "dataset" / "ctf_docker_nyu_subtask_cases.txt"
MANIFEST_PATH = (
    HAORAN_ROOT / "SubtaskGen" / "export4manual_review" / "final_metadata_manifest.csv"
)


def _load_manifest_rows() -> List[Dict[str, str]]:
    with MANIFEST_PATH.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _copy_one_challenge(rel_path: str, metadata_export_path: str) -> None:
    src_dir = SOURCE_BENCHMARK_ROOT / rel_path
    dst_dir = TARGET_BENCHMARK_ROOT / rel_path
    if not src_dir.is_dir():
        raise FileNotFoundError(f"Source NYU challenge directory not found: {src_dir}")

    dst_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(src_dir, dst_dir, dirs_exist_ok=True)

    metadata_dir = dst_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    src_metadata = HAORAN_ROOT / metadata_export_path.lstrip("/")
    if not src_metadata.is_file():
        raise FileNotFoundError(f"Reviewed metadata export not found: {src_metadata}")
    shutil.copy2(src_metadata, metadata_dir / "metadata.json")


def _build_subset_index(selected_rel_paths: List[str]) -> Dict[str, Dict[str, str]]:
    source_index = json.loads(SOURCE_INDEX_PATH.read_text(encoding="utf-8"))
    selected_set = {f"nyu_ctf/{rel_path}" for rel_path in selected_rel_paths}
    subset: Dict[str, Dict[str, str]] = {}
    for key, value in source_index.items():
        if value.get("path") not in selected_set:
            continue
        copied = dict(value)
        copied["path"] = str(copied["path"]).replace("nyu_ctf/", "nyu_ctf_subtask/", 1)
        subset[key] = copied
    return subset


def _load_source_docker_cases() -> List[str]:
    rows: List[str] = []
    for raw_line in SOURCE_DOCKER_CASE_LIST.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip().strip("/").replace("\\", "/")
        if not line or line.startswith("#"):
            continue
        rows.append(line)
    return rows


def main() -> int:
    rows = _load_manifest_rows()
    rel_paths = [row["benchmark_rel_path"] for row in rows]

    TARGET_BENCHMARK_ROOT.mkdir(parents=True, exist_ok=True)
    for row in rows:
        _copy_one_challenge(
            rel_path=row["benchmark_rel_path"],
            metadata_export_path=row["export_metadata_path"],
        )

    subset_index = _build_subset_index(rel_paths)
    expected_paths = {f"nyu_ctf_subtask/{rel_path}" for rel_path in rel_paths}
    actual_paths = {entry["path"] for entry in subset_index.values()}
    missing_paths = sorted(expected_paths - actual_paths)
    if missing_paths:
        raise RuntimeError(
            "Missing nyu_ctf.json entries for reviewed benchmark paths: "
            + ", ".join(missing_paths[:10])
            + (" ..." if len(missing_paths) > 10 else "")
        )

    TARGET_INDEX_PATH.write_text(
        json.dumps(subset_index, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    source_docker_cases = set(_load_source_docker_cases())
    docker_backed_rel_paths = [
        rel_path
        for rel_path in rel_paths
        if f"nyu_ctf/{rel_path}" in source_docker_cases
    ]
    TARGET_CASE_LIST.write_text(
        "\n".join(f"nyu_ctf_subtask/{rel_path}" for rel_path in docker_backed_rel_paths)
        + "\n",
        encoding="utf-8",
    )

    summary = {
        "source_benchmark_root": str(SOURCE_BENCHMARK_ROOT),
        "target_benchmark_root": str(TARGET_BENCHMARK_ROOT),
        "manifest_path": str(MANIFEST_PATH),
        "target_index_path": str(TARGET_INDEX_PATH),
        "target_case_list": str(TARGET_CASE_LIST),
        "copied_challenge_count": len(rel_paths),
        "docker_backed_case_count": len(docker_backed_rel_paths),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
