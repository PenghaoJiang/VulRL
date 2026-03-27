#!/usr/bin/env python3
"""Audit all CTF benchmark challenges for CTFMix conversion/schema health."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


VULRL_ROOT = Path(__file__).resolve().parents[1]
SKYRL_VULRL_ROOT = VULRL_ROOT / "SkyRL" / "skyrl-train" / "vulrl_inside_skyrl"

sys.path.insert(0, str(VULRL_ROOT))
sys.path.insert(0, str(SKYRL_VULRL_ROOT))

from dataset.dataset_converter import CTFToUnifiedConverter  # noqa: E402
from vulrl.ctfmix.prompt import (  # noqa: E402
    get_default_prompt_config_path,
    load_default_agent_config,
)
from vulrl.ctfmix.runtime import RuntimeTask  # noqa: E402


def discover_challenge_dirs(root: Path) -> list[Path]:
    converter = CTFToUnifiedConverter()
    return converter._discover_ctf_challenge_dirs(root)


def family_for(root: Path, challenge_dir: Path) -> str:
    rel = challenge_dir.resolve().relative_to(root.resolve())
    return rel.parts[0]


def task_id_for(root: Path, challenge_dir: Path) -> str:
    converter = CTFToUnifiedConverter()
    return converter._build_task_id(root, challenge_dir)


def validate_row_schema(row: dict[str, Any]) -> list[str]:
    issues: list[str] = []

    required_top = {"prompt", "env_class", "env_config", "poc_info", "tools", "task_id", "metadata"}
    missing_top = sorted(required_top - set(row))
    if missing_top:
        issues.append(f"missing_top_keys:{','.join(missing_top)}")

    prompt = row.get("prompt")
    if not isinstance(prompt, list) or not prompt:
        issues.append("invalid_prompt_type")
    else:
        for index, message in enumerate(prompt):
            if not isinstance(message, dict):
                issues.append(f"prompt_item_not_dict:{index}")
                continue
            if "role" not in message or "content" not in message:
                issues.append(f"prompt_item_missing_keys:{index}")

    if row.get("env_class") != "vulrl.SecurityEnv":
        issues.append(f"unexpected_env_class:{row.get('env_class')}")

    env_config = row.get("env_config")
    if not isinstance(env_config, dict):
        issues.append("invalid_env_config_type")
        return issues

    required_env = {
        "task_id",
        "task_type",
        "max_steps",
        "timeout",
        "target_host",
        "target_port",
        "target_protocol",
        "command_config",
        "poc_info",
        "backend_config",
    }
    missing_env = sorted(required_env - set(env_config))
    if missing_env:
        issues.append(f"missing_env_config_keys:{','.join(missing_env)}")

    if env_config.get("task_type") != "ctfmix":
        issues.append(f"unexpected_task_type:{env_config.get('task_type')}")

    backend_config = env_config.get("backend_config")
    if not isinstance(backend_config, dict):
        issues.append("invalid_backend_config_type")
        return issues

    required_backend = {
        "task_id",
        "name",
        "description",
        "category",
        "flag_format",
        "server_description",
        "box",
        "internal_port",
        "repo_path",
        "files",
        "command_config",
        "exclude_paths",
        "expose_flag_to_agent",
        "hide_solution_artifacts",
    }
    missing_backend = sorted(required_backend - set(backend_config))
    if missing_backend:
        issues.append(f"missing_backend_keys:{','.join(missing_backend)}")

    return issues


def audit_challenge(
    converter: CTFToUnifiedConverter,
    root: Path,
    challenge_dir: Path,
    agent_config,
    prompt_config_path: str,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "challenge_dir": str(challenge_dir.resolve()),
        "family": family_for(root, challenge_dir),
        "task_id": task_id_for(root, challenge_dir),
        "issues": [],
        "warnings": [],
    }

    try:
        challenge_data = converter._load_ctf_challenge_data(challenge_dir)
    except Exception as exc:
        result["issues"].append(f"load_failed:{type(exc).__name__}:{exc}")
        result["ok"] = False
        return result

    result.update(
        {
            "category": challenge_data.get("category"),
            "files_count": len(challenge_data.get("files") or []),
            "compose_path": challenge_data.get("compose_path"),
            "target_host": challenge_data.get("box"),
            "target_port": challenge_data.get("internal_port"),
            "target_protocol": challenge_data.get("target_protocol"),
            "server_description": challenge_data.get("server_description"),
        }
    )

    manifest_files = challenge_data.get("files") or []
    missing_manifest_entries = [
        relative_path
        for relative_path in manifest_files
        if not (challenge_dir / relative_path).exists()
    ]
    if missing_manifest_entries:
        result["issues"].append(
            f"manifest_missing_paths:{','.join(missing_manifest_entries[:10])}"
        )
        result["missing_manifest_entries"] = missing_manifest_entries

    challenge_json = challenge_data.get("challenge_json") or {}
    compose_declared = bool(challenge_json.get("compose"))
    result["compose_declared"] = compose_declared
    if compose_declared and not challenge_data.get("compose_path"):
        result["issues"].append("compose_declared_but_path_missing")

    if manifest_files == [".placeholder"]:
        result["warnings"].append("placeholder_manifest_only")
    elif not manifest_files:
        result["warnings"].append("empty_manifest")

    if not challenge_data.get("compose_path"):
        host = str(challenge_data.get("box") or "").strip()
        port = int(challenge_data.get("internal_port") or 0)
        has_endpoint = bool(host and port > 0)
        has_local_artifacts = bool(manifest_files and manifest_files != [".placeholder"])
        if not has_endpoint and not has_local_artifacts:
            result["warnings"].append("prompt_only_challenge")
        elif not has_endpoint:
            result["warnings"].append("file_only_challenge_no_endpoint")

    row: dict[str, Any] | None = None
    try:
        row = converter._ctf_challenge_to_skyrl(
            challenge_dir=challenge_dir,
            root_dir=root,
            variant="zero_day",
            agent_config=agent_config,
            prompt_config_path=prompt_config_path,
        )
    except Exception as exc:
        result["issues"].append(f"row_build_failed:{type(exc).__name__}:{exc}")

    if row is not None:
        schema_issues = validate_row_schema(row)
        result["issues"].extend(schema_issues)

        backend_config = row["env_config"]["backend_config"]
        try:
            RuntimeTask.from_dict(backend_config)
        except Exception as exc:
            result["issues"].append(f"runtime_task_invalid:{type(exc).__name__}:{exc}")

        backend_repo_path = Path(backend_config["repo_path"])
        if backend_repo_path.resolve() != challenge_dir.resolve():
            result["issues"].append("repo_path_mismatch")

        if backend_config.get("files") != manifest_files:
            result["issues"].append("manifest_mismatch_between_row_and_challenge")

        if backend_config.get("compose_path") and not Path(backend_config["compose_path"]).exists():
            result["issues"].append("backend_compose_path_missing")

        if not isinstance(row.get("metadata"), dict):
            result["issues"].append("invalid_metadata_type")

    result["ok"] = not result["issues"]
    return result


def print_summary(results: list[dict[str, Any]]) -> None:
    by_family: dict[str, Counter] = defaultdict(Counter)
    issue_counter: Counter[str] = Counter()

    for result in results:
        family = result["family"]
        by_family[family]["total"] += 1
        if result["ok"]:
            by_family[family]["ok"] += 1
        else:
            by_family[family]["failed"] += 1
        for issue in result["issues"]:
            issue_counter[issue.split(":", 1)[0]] += 1
        for warning in result["warnings"]:
            by_family[family][f"warning:{warning}"] += 1

    print("=" * 80)
    print("CTFMix Benchmark Audit Summary")
    print("=" * 80)
    total_ok = sum(1 for result in results if result["ok"])
    print(f"Total challenges: {len(results)}")
    print(f"Passed schema audit: {total_ok}")
    print(f"Failed schema audit: {len(results) - total_ok}")
    print("")

    for family in sorted(by_family):
        counts = by_family[family]
        print(
            f"[{family}] total={counts['total']} ok={counts['ok']} failed={counts['failed']} "
            f"empty_manifest={counts['warning:empty_manifest']} "
            f"placeholder_manifest={counts['warning:placeholder_manifest_only']} "
            f"file_only_no_endpoint={counts['warning:file_only_challenge_no_endpoint']} "
            f"prompt_only={counts['warning:prompt_only_challenge']}"
        )

    print("")
    print("Top issue types:")
    for issue, count in issue_counter.most_common(20):
        print(f"  - {issue}: {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit CTF benchmark conversion/runtime schema.")
    parser.add_argument(
        "--bench-root",
        default=str(VULRL_ROOT / "benchmark" / "ctfmix"),
        help="Path to benchmark root directory",
    )
    parser.add_argument(
        "--output-json",
        default=str(VULRL_ROOT / "infra" / "outputs" / "ctfmix_benchmark_audit.json"),
        help="Where to write full JSON audit results",
    )
    args = parser.parse_args()

    bench_root = Path(args.bench_root).expanduser().resolve()
    output_json = Path(args.output_json).expanduser().resolve()

    converter = CTFToUnifiedConverter()
    agent_config = load_default_agent_config()
    prompt_config_path = str(get_default_prompt_config_path().resolve())
    challenge_dirs = discover_challenge_dirs(bench_root)

    results = [
        audit_challenge(
            converter=converter,
            root=bench_root,
            challenge_dir=challenge_dir,
            agent_config=agent_config,
            prompt_config_path=prompt_config_path,
        )
        for challenge_dir in challenge_dirs
    ]

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    print_summary(results)
    print("")
    print(f"Detailed results written to {output_json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
