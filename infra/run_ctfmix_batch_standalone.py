from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def _ensure_paths() -> Path:
    current = Path(__file__).resolve()
    vulrl_repo = current.parent.parent / "SkyRL" / "skyrl-train" / "vulrl_inside_skyrl"
    skyrl_train = current.parent.parent / "SkyRL" / "skyrl-train"
    skyrl_gym = current.parent.parent / "SkyRL" / "skyrl-gym"
    repo_root = current.parent.parent

    for path in [vulrl_repo, skyrl_train, skyrl_gym, repo_root]:
        if str(path) not in sys.path:
            sys.path.insert(0, str(path))
    return repo_root


REPO_ROOT = _ensure_paths()

from dataset.dataset_converter import CTFToUnifiedConverter
from vulrl.ctfmix.prompt import get_default_prompt_config_path, load_default_agent_config
from vulrl.ctfmix.runtime import CTFMixRuntime, RuntimeTask
from vulrl.ctfmix.standalone import run_agent


def load_audit_rows(audit_path: Path) -> list[dict]:
    rows = json.loads(audit_path.read_text())
    if not isinstance(rows, list):
        raise ValueError(f"Unexpected audit format in {audit_path}")
    return rows


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_completed_task_ids(results_path: Path) -> set[str]:
    if not results_path.exists():
        return set()
    completed: set[str] = set()
    for line in results_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        task_id = row.get("task_id")
        if task_id:
            completed.add(task_id)
    return completed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Batch standalone smoke runner for ctfmix benchmarks")
    parser.add_argument(
        "--audit",
        default=str(REPO_ROOT / "infra" / "outputs" / "ctfmix_benchmark_audit.json"),
        help="Path to the benchmark audit json",
    )
    parser.add_argument(
        "--results",
        default=str(REPO_ROOT / "infra" / "outputs" / "ctfmix_agent_smoke" / "batch_results.jsonl"),
        help="Path to append per-task batch results",
    )
    parser.add_argument(
        "--traj-dir",
        default=str(REPO_ROOT / "infra" / "outputs" / "ctfmix_agent_smoke"),
        help="Directory to store trajectory files",
    )
    parser.add_argument("--model-name", default="gpt-4.1-nano")
    parser.add_argument("--step-limit", type=int, default=3)
    parser.add_argument("--family", action="append", help="Optional benchmark family filter, e.g. cybench")
    parser.add_argument("--limit", type=int, default=0, help="Optional max number of tasks to run (0 = all)")
    parser.add_argument("--skip-existing-traj", action="store_true", default=True)
    args = parser.parse_args(argv)

    audit_path = Path(args.audit).expanduser().resolve()
    results_path = Path(args.results).expanduser().resolve()
    traj_dir = Path(args.traj_dir).expanduser().resolve()
    traj_dir.mkdir(parents=True, exist_ok=True)

    rows = load_audit_rows(audit_path)
    rows = [row for row in rows if row.get("ok")]
    if args.family:
        allowed = set(args.family)
        rows = [row for row in rows if row.get("family") in allowed]

    completed_task_ids = load_completed_task_ids(results_path)
    prompt_config_path = str(get_default_prompt_config_path().resolve())
    agent_config = load_default_agent_config()
    converter = CTFToUnifiedConverter()
    bench_root = REPO_ROOT / "benchmark" / "ctfmix"

    pending: list[dict] = []
    for row in rows:
        task_id = row["task_id"]
        traj_path = traj_dir / f"{task_id}.traj"
        if task_id in completed_task_ids:
            continue
        if args.skip_existing_traj and traj_path.exists():
            continue
        pending.append(row)

    if args.limit > 0:
        pending = pending[: args.limit]

    print(f"total_ok={len(rows)} pending={len(pending)} model={args.model_name} step_limit={args.step_limit}")
    start_batch = time.time()

    for index, row in enumerate(pending, start=1):
        challenge_dir = Path(row["challenge_dir"]).resolve()
        task_id = row["task_id"]
        started_at = time.time()
        print(f"[{index}/{len(pending)}] START {task_id} :: {challenge_dir}")
        payload = {
            "task_id": task_id,
            "family": row.get("family"),
            "challenge_dir": str(challenge_dir),
            "model_name": args.model_name,
            "step_limit": args.step_limit,
            "started_at": started_at,
        }
        try:
            converted = converter._ctf_challenge_to_skyrl(
                challenge_dir,
                bench_root,
                "zero_day",
                agent_config,
                prompt_config_path,
            )
            task = RuntimeTask.from_dict(converted["env_config"]["backend_config"])
            with CTFMixRuntime(task, config_path=prompt_config_path) as runtime:
                rc = run_agent(
                    runtime,
                    config_path=prompt_config_path,
                    model_name=args.model_name,
                    temperature=0.0,
                    top_p=1.0,
                    top_k=20,
                    step_limit=args.step_limit,
                    traj_dir=traj_dir,
                )
            payload.update(
                {
                    "status": "ok",
                    "return_code": rc,
                    "traj_path": str(traj_dir / f"{task_id}.traj"),
                    "duration_sec": round(time.time() - started_at, 3),
                }
            )
            print(f"[{index}/{len(pending)}] END {task_id} rc={rc}")
        except Exception as exc:
            payload.update(
                {
                    "status": "error",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "duration_sec": round(time.time() - started_at, 3),
                }
            )
            print(f"[{index}/{len(pending)}] ERROR {task_id}: {type(exc).__name__}: {exc}")
        append_jsonl(results_path, payload)

    print(f"batch_duration_sec={round(time.time() - start_batch, 3)} results={results_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
