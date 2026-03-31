"""Standalone runner for CTFMix without Ray/SkyRL."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml

from .agents import Agent, AgentArguments
from .config import find_ctfmix_benchmark_root, find_vulrl_repo_root
from .models import ModelArguments
from .prompt import get_default_prompt_config_path, load_default_agent_config
from .runtime import CTFMixRuntime, RuntimeTask


def load_task_file(task_file: str | Path) -> RuntimeTask:
    task_path = Path(task_file).expanduser().resolve()
    data = yaml.safe_load(task_path.read_text())
    for key in ("compose_path", "repo_path", "flag_check", "command_config"):
        value = data.get(key)
        if value:
            data[key] = str((task_path.parent / value).resolve()) if not Path(value).is_absolute() else value
    return RuntimeTask.from_dict(data)


def load_challenge_dir(
    challenge_dir: str | Path,
    *,
    bench_root: str | Path | None = None,
    variant: str = "zero_day",
    config_path: str | Path | None = None,
) -> RuntimeTask:
    from dataset.dataset_converter import CTFToUnifiedConverter

    challenge_path = Path(challenge_dir).expanduser().resolve()
    root = Path(bench_root).expanduser().resolve() if bench_root else find_ctfmix_benchmark_root()
    prompt_config_path = str(Path(config_path).expanduser().resolve()) if config_path else str(get_default_prompt_config_path())
    converter = CTFToUnifiedConverter()
    row = converter._ctf_challenge_to_skyrl(
        challenge_dir=challenge_path,
        root_dir=root,
        variant=variant,
        agent_config=load_default_agent_config(prompt_config_path),
        prompt_config_path=prompt_config_path,
    )
    return RuntimeTask.from_dict(row["env_config"]["backend_config"])


def run_scripted(runtime: CTFMixRuntime, commands_file: str | Path) -> int:
    prompt, _ = runtime.reset()
    print(prompt)
    for raw_line in Path(commands_file).read_text().splitlines():
        command = raw_line.strip()
        if not command or command.startswith("#"):
            continue
        observation, _, done, info = runtime.step(command)
        print(f"$ {command}")
        if observation:
            print(observation)
        if done:
            print(info)
            return 0 if info.get("score", 0.0) > 0 else 1
    return 0


def run_repl(runtime: CTFMixRuntime) -> int:
    prompt, _ = runtime.reset()
    print(prompt)
    while True:
        try:
            command = input("ctfmix> ").strip()
        except EOFError:
            return 0
        if not command:
            continue
        if command in {"quit", "exit"}:
            return 0
        observation, _, done, info = runtime.step(command)
        if observation:
            print(observation)
        if done:
            print(info)
            return 0 if info.get("score", 0.0) > 0 else 1


def run_agent(
    runtime: CTFMixRuntime,
    *,
    config_path: str | Path | None,
    model_name: str,
    temperature: float,
    top_p: float,
    top_k: int,
    step_limit: int,
    traj_dir: str | Path | None,
) -> int:
    initial_observation, _ = runtime.reset()
    trajectory_root = Path(traj_dir).expanduser().resolve() if traj_dir else find_vulrl_repo_root() / "infra" / "outputs" / "ctfmix_agent"
    trajectory_root.mkdir(parents=True, exist_ok=True)
    prompt_task = runtime.build_prompt_task_payload()
    setup_args = {
        **prompt_task,
        "files": ", ".join(prompt_task["files"]) or "none",
    }
    agent = Agent(
        "primary",
        AgentArguments(
            model=ModelArguments(
                model_name=model_name,
                temperature=temperature,
                top_p=top_p,
                top_k=top_k,
                per_instance_step_limit=step_limit,
            ),
            config_file=Path(config_path or get_default_prompt_config_path()),
        ),
    )
    info, trajectory = agent.run(
        setup_args,
        runtime,
        observation=initial_observation,
        traj_dir=trajectory_root,
        return_type="info_trajectory",
    )
    print(json.dumps(info, indent=2, ensure_ascii=False))
    print(f"trajectory_path={trajectory_root / (runtime.task.task_id + '.traj')}")
    return 0 if info.get("score", 0.0) > 0 else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a CTF task with the CTFMix runtime")
    parser.add_argument("--task", help="Path to a normalized RuntimeTask YAML file")
    parser.add_argument("--challenge-dir", help="Path to a benchmark challenge directory to normalize on the fly")
    parser.add_argument("--bench-root", help="Optional benchmark root used to derive task_id for --challenge-dir")
    parser.add_argument("--variant", default="zero_day", choices=["zero_day", "one_day"], help="Dataset variant used with --challenge-dir")
    parser.add_argument("--config", help="Path to an enigma+ prompt config yaml")
    parser.add_argument("--commands", help="Optional scripted commands file")
    parser.add_argument("--model-name", help="Run the OpenAI/enigma-style agent with this model")
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature for agent mode")
    parser.add_argument("--top-p", type=float, default=1.0, help="Sampling top-p for agent mode")
    parser.add_argument("--top-k", type=int, default=20, help="Sampling top-k for agent mode")
    parser.add_argument("--step-limit", type=int, default=30, help="Maximum agent steps in agent mode")
    parser.add_argument("--traj-dir", help="Directory to write agent trajectories into")
    args = parser.parse_args(argv)

    if bool(args.task) == bool(args.challenge_dir):
        parser.error("Exactly one of --task or --challenge-dir must be provided")

    if args.task:
        task = load_task_file(args.task)
    else:
        task = load_challenge_dir(
            args.challenge_dir,
            bench_root=args.bench_root,
            variant=args.variant,
            config_path=args.config,
        )
    with CTFMixRuntime(task, config_path=args.config) as runtime:
        if args.commands:
            return run_scripted(runtime, args.commands)
        if args.model_name:
            return run_agent(
                runtime,
                config_path=args.config,
                model_name=args.model_name,
                temperature=args.temperature,
                top_p=args.top_p,
                top_k=args.top_k,
                step_limit=args.step_limit,
                traj_dir=args.traj_dir,
            )
        return run_repl(runtime)


if __name__ == "__main__":
    raise SystemExit(main())
