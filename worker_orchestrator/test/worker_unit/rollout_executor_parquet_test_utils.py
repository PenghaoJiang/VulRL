"""
Shared helpers for parquet-backed RolloutExecutor smoke tests.

These helpers intentionally exercise the same higher-level path as training:
dataset conversion -> parquet row -> RolloutRequest -> RolloutExecutor.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Dict, Iterator, Tuple, Type

import pandas as pd

WORKER_ORCH_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = WORKER_ORCH_ROOT.parent
HAORAN_ROOT = REPO_ROOT.parent
SUBTASKGEN_ENV_PATH = HAORAN_ROOT / "SubtaskGen" / ".env"
OUTPUT_ROOT = WORKER_ORCH_ROOT / "test" / "output" / "rollout_executor_parquet"

sys.path.insert(0, str(WORKER_ORCH_ROOT))
sys.path.insert(0, str(REPO_ROOT))

from dataset.dataset_converter_ctf import _convert_one
from worker_router.models import RolloutRequest, RolloutResult
from worker_unit.rollout_executor import RolloutExecutor
import worker_unit.rollout_executor as rollout_executor_module


DEFAULT_CHALLENGE_REL_PATH = "cybench/HKC/web/22-back-to-the-past"
DEFAULT_TASK_TYPE = "cybench_docker"
DEFAULT_TIMEOUT = 30


class _TeeStream:
    def __init__(self, *streams) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for stream in self._streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self._streams:
            stream.flush()

    def isatty(self) -> bool:
        return False


def _jsonable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    return value


def ensure_output_dir(name: str) -> Path:
    path = OUTPUT_ROOT / name
    path.mkdir(parents=True, exist_ok=True)
    return path


@contextmanager
def tee_output(log_path: Path) -> Iterator[None]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8", buffering=1) as log_file:
        tee_stdout = _TeeStream(sys.__stdout__, log_file)
        tee_stderr = _TeeStream(sys.__stderr__, log_file)
        with redirect_stdout(tee_stdout), redirect_stderr(tee_stderr):
            logging.basicConfig(level=logging.INFO, stream=sys.stderr, force=True)
            yield


@contextmanager
def patch_rollout_llm_client(replacement: Type[Any]) -> Iterator[None]:
    original = rollout_executor_module.InferenceEngineClientWrapper
    rollout_executor_module.InferenceEngineClientWrapper = replacement
    try:
        yield
    finally:
        rollout_executor_module.InferenceEngineClientWrapper = original


def build_single_case_parquet(
    *,
    output_dir: Path,
    rel_path: str = DEFAULT_CHALLENGE_REL_PATH,
    task_type: str = DEFAULT_TASK_TYPE,
    max_steps: int,
    timeout: int = DEFAULT_TIMEOUT,
) -> Path:
    ctfmix_root = REPO_ROOT / "benchmark" / "ctfmix"
    row = _convert_one(
        rel_path=rel_path,
        task_type=task_type,
        ctfmix_root=ctfmix_root,
        max_steps=max_steps,
        timeout=timeout,
        tools_json="[]",
        seen_ids={},
    )
    parquet_path = output_dir / "input_case.parquet"
    pd.DataFrame([row]).to_parquet(parquet_path, index=False)
    (output_dir / "converted_row.json").write_text(
        json.dumps(_jsonable(row), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"[TestUtils] Wrote parquet fixture to {parquet_path}")
    return parquet_path


def _extract_prompt_text(prompt_value: Any) -> str:
    prompt_payload = prompt_value
    if isinstance(prompt_payload, str):
        prompt_payload = json.loads(prompt_payload)
    if isinstance(prompt_payload, list):
        for message in reversed(prompt_payload):
            if isinstance(message, dict) and message.get("role") == "user":
                return str(message.get("content") or "")
    return str(prompt_payload)


def _extract_metadata(metadata_value: Any) -> Dict[str, Any]:
    if isinstance(metadata_value, str):
        return dict(json.loads(metadata_value))
    return dict(metadata_value or {})


def build_rollout_request_from_parquet(
    parquet_path: Path,
    *,
    llm_endpoint: str,
    model_name: str,
    max_steps: int,
    temperature: float,
    max_tokens: int,
) -> RolloutRequest:
    df = pd.read_parquet(parquet_path)
    if len(df) != 1:
        raise ValueError(f"Expected a single-row parquet, got {len(df)} rows")
    row = df.iloc[0].to_dict()
    metadata = _extract_metadata(row["metadata"])
    request = RolloutRequest(
        cve_id=str(row["cve_id"]),
        vulhub_path=str(row.get("vulhub_path") or ""),
        prompt=_extract_prompt_text(row["prompt"]),
        max_steps=max_steps,
        timeout=int(metadata.get("timeout") or DEFAULT_TIMEOUT),
        llm_endpoint=llm_endpoint,
        model_name=model_name,
        temperature=temperature,
        max_tokens=max_tokens,
        metadata=metadata,
    )
    return request


def save_request(output_dir: Path, request: RolloutRequest) -> Path:
    path = output_dir / "rollout_request.json"
    path.write_text(
        json.dumps(_jsonable(request), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def save_result(output_dir: Path, result: RolloutResult) -> Path:
    path = output_dir / "rollout_result.json"
    path.write_text(
        json.dumps(_jsonable(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    trajectory_path = output_dir / "trajectory.jsonl"
    trajectory_rows = []
    for step in result.trajectory or []:
        trajectory_rows.append(json.dumps(_jsonable(step), ensure_ascii=False))
    trajectory_path.write_text("\n".join(trajectory_rows) + ("\n" if trajectory_rows else ""), encoding="utf-8")
    return path


async def run_rollout_executor(
    *,
    request: RolloutRequest,
    output_dir: Path,
    llm_client_cls: Type[Any],
    agent_type: str = "ctf",
) -> RolloutResult:
    log_path = output_dir / "run.log"
    with tee_output(log_path), patch_rollout_llm_client(llm_client_cls):
        print(f"[TestUtils] Output directory: {output_dir}")
        print(f"[TestUtils] Agent type: {agent_type}")
        print(f"[TestUtils] Request model={request.model_name} endpoint={request.llm_endpoint}")
        save_request(output_dir, request)
        started_at = time.time()
        executor = RolloutExecutor()
        result = await executor.execute(request, agent_type=agent_type)
        finished_at = time.time()
        save_result(output_dir, result)
        summary = {
            "started_at": started_at,
            "finished_at": finished_at,
            "duration_sec": finished_at - started_at,
            "reward": result.reward,
            "success": result.success,
            "status": result.status,
            "trajectory_steps": len(result.trajectory or []),
            "log_path": str(log_path),
        }
        (output_dir / "summary.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[TestUtils] Saved rollout result to {output_dir / 'rollout_result.json'}")
        return result


def load_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.is_file():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        values[key] = value
    return values


def ensure_openai_api_key() -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "").strip()
    if api_key:
        return api_key
    file_values = load_env_file(SUBTASKGEN_ENV_PATH)
    api_key = str(file_values.get("OPENAI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError(
            f"OPENAI_API_KEY not set and no key found in {SUBTASKGEN_ENV_PATH}"
        )
    os.environ["OPENAI_API_KEY"] = api_key
    return api_key


def assert_rollout_completed(result: RolloutResult) -> None:
    if result.status != "completed":
        raise AssertionError(
            f"Expected rollout status=completed, got {result.status} error={result.error!r}"
        )
    if not result.trajectory:
        raise AssertionError("Expected a non-empty trajectory")
