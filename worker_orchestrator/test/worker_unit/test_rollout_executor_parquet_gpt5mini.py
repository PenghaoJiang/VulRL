"""
Parquet-backed RolloutExecutor smoke test with a real OpenAI model.

This uses the same high-level path as training, but monkeypatches the worker's
LLM client wrapper to call OpenAI directly so the test can run without vLLM.
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List

from openai import AsyncOpenAI

from rollout_executor_parquet_test_utils import (
    assert_rollout_completed,
    build_rollout_request_from_parquet,
    build_single_case_parquet,
    ensure_openai_api_key,
    ensure_output_dir,
    run_rollout_executor,
)
class OpenAIInferenceEngineClientWrapper:
    def __init__(self, endpoint: str, model_name: str) -> None:
        api_key = ensure_openai_api_key()
        self.endpoint = endpoint.rstrip("/") or "https://api.openai.com/v1"
        self.model_name = model_name
        self.client = AsyncOpenAI(api_key=api_key, base_url=self.endpoint)
        self.calls = 0
        print(
            f"[OpenAIWrapper] Initialized real client endpoint={self.endpoint} model={self.model_name}"
        )

    async def _call_chat_api(
        self,
        messages: List[Dict[str, str]],
        *,
        max_tokens: int,
    ) -> str:
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_completion_tokens=max_tokens,
        )
        content = response.choices[0].message.content
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text") or ""))
            return "".join(parts).strip()
        return str(content or "")

    async def generate(self, input_batch):
        self.calls += 1
        messages = list(input_batch["prompts"][0])
        sampling = dict(input_batch.get("sampling_params") or {})
        max_tokens = int(sampling.get("max_tokens") or 512)
        print(
            f"[OpenAIWrapper] Request #{self.calls}: messages={len(messages)} max_completion_tokens={max_tokens}"
        )
        text = await self._call_chat_api(
            messages,
            max_tokens=max_tokens,
        )
        print(f"[OpenAIWrapper] Response #{self.calls} preview={text[:400]!r}")
        return {
            "responses": [text],
            "stop_reasons": ["stop"],
            "response_ids": [[f"openai-{self.calls}"]],
        }


async def main() -> int:
    output_dir = ensure_output_dir("gpt5mini")
    parquet_path = build_single_case_parquet(
        output_dir=output_dir,
        max_steps=20,
    )
    request = build_rollout_request_from_parquet(
        parquet_path,
        llm_endpoint="https://api.openai.com/v1",
        model_name="gpt-5-mini",
        max_steps=20,
        temperature=0.2,
        max_tokens=768,
    )
    result = await run_rollout_executor(
        request=request,
        output_dir=output_dir,
        llm_client_cls=OpenAIInferenceEngineClientWrapper,
    )
    assert_rollout_completed(result)
    print(
        f"[RealExecutorTest] Completed status={result.status} reward={result.reward} steps={len(result.trajectory or [])}"
    )
    print(f"[RealExecutorTest] Artifacts saved under {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
