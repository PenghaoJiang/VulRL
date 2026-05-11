"""
Docker-backed Cybench smoke test for subtask prompt/reward plumbing.

This script exercises the real worker-side runtime path:
dataset row -> SecurityEnv/CybenchDockerAdapter -> CTFAgent -> runtime adapter
-> CybenchFlagReward.

It uses a fake LLM so it does not require vLLM or SkyRL, but it does require
Docker access for the challenge environment.
"""

import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from dataset.dataset_converter_ctf import _convert_one
from worker_unit.agent.ctf_agent import CTFAgent
from worker_unit.env.security_env import SecurityEnv
from worker_unit.reward.task_specific.cybench_flag_reward import CybenchFlagReward


class FakeLLMClient:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, input_batch):
        self.calls += 1
        if self.calls == 1:
            response = """DISCUSSION
I have enough evidence for the first Cybench checkpoint, so I will record it before doing anything else.
```
submit_subtask 1 '.git'
```"""
        else:
            response = """DISCUSSION
I only wanted to verify the checkpoint logging path in this smoke test, so I will stop now.
```
exit_forfeit
```"""
        return {
            "responses": [response],
            "stop_reasons": ["stop"],
            "response_ids": [[]],
        }


async def main() -> int:
    repo_root = Path(__file__).resolve().parents[3]
    ctfmix_root = repo_root / "benchmark" / "ctfmix"
    row = _convert_one(
        rel_path="cybench/HKC/web/22-back-to-the-past",
        task_type="cybench_docker",
        ctfmix_root=ctfmix_root,
        max_steps=4,
        timeout=30,
        tools_json="[]",
        seen_ids={},
    )
    prompt = json.loads(row["prompt"])[-1]["content"]
    metadata = json.loads(row["metadata"])

    env = SecurityEnv(
        config={
            "task_type": "cybench_docker",
            "task_id": row["cve_id"],
            "max_steps": 4,
            "timeout": 30,
            "parquet_metadata": metadata,
            "ctfmix_root": metadata["ctfmix_root"],
            "challenge_relative_path": metadata["challenge_relative_path"],
            "backend_config": {
                "parquet_metadata": metadata,
                "ctfmix_root": metadata["ctfmix_root"],
                "challenge_relative_path": metadata["challenge_relative_path"],
            },
        }
    )

    try:
        agent = CTFAgent(
            env=env.adapter,
            llm_client=FakeLLMClient(),
            config={
                "model_name": "gpt-4.1-nano",
                "temperature": 0.0,
                "max_tokens": 256,
                "step_limit": 4,
            },
        )
        trajectory = await agent.run(initial_prompt=prompt, max_steps=4)
        traj_dicts = [step.model_dump() for step in trajectory]
        reward = CybenchFlagReward(
            {
                "expected_flag": metadata.get("expected_flag"),
                "ctfmix_supported": True,
                "flag_format": metadata.get("flag_format", "flag{...}"),
                "cybench_subtasks": metadata.get("cybench_subtasks", []),
                "subtask_reward_weight": metadata.get("subtask_reward_weight", 0.1),
            }
        ).compute(traj_dicts, metadata["challenge_relative_path"])

        print("TRAJECTORY_STEPS=", len(traj_dicts))
        for step in traj_dicts:
            print("STEP", step["step"], "ACTION=", step["action"])
            print("OBS=", (step["observation"] or "")[:400])
        print("FAKE_ROLLOUT_REWARD=", reward)
        return 0
    finally:
        env.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
