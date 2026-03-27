# CTFMix Handoff

This document describes the `ctfmix` integration that brings enigma-style CTF solving into the inner VulRL repo.

## What Was Added

Compared with the original SkyRL-based VulRL tree, this integration adds a CTF runtime, standalone entrypoints, benchmark conversion, and CTF-specific environment wiring.

Main new code lives under:

- `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/ctfmix`
- `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/docker1/adapters/ctfmix_adapter.py`
- `/VulRL/infra/ctfmix_run.py`
- `/VulRL/infra/run_ctfmix_batch_standalone.py`
- `/VulRL/dataset/dataset_converter.py`

Copied repo-local assets now live under:

- `/VulRL/benchmark/ctfmix`
- `/VulRL/benchmark/ctfmix/config`
- `/VulRL/benchmark/ctfmix/models_config.yaml`

## Architecture

The runtime keeps the existing VulRL shell:

`SecurityEnv -> Adapter -> Runtime`

For `ctfmix`, the concrete path is:

`SecurityEnv`
- file: `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/env/security_env.py`
- role: SkyRL/Gym-facing environment wrapper

`CTFMixAdapter`
- file: `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/docker1/adapters/ctfmix_adapter.py`
- role: adapter between `SecurityEnv` and the enigma-style runtime

`CTFMixRuntime`
- file: `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/ctfmix/runtime.py`
- role: long-lived agent container, command installation, challenge reset, compose/network handling, interactive sessions, submit validation, terminal reward

Supporting modules:

- `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/ctfmix/runtime_utils.py`
  dynamic compose, dynamic ports, Docker network helpers, timeout readers
- `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/ctfmix/commands.py`
  enigma-style command parsing
- `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/ctfmix/interactive_commands.py`
  debug/connect interactive sessions
- `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/ctfmix/agents.py`
  standalone agent loop, parser/model wiring, `AgentConfig`
- `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/ctfmix/prompt.py`
  prompt loading from repo-local `benchmark/ctfmix/config/default_ctf.yaml`
- `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/ctfmix/models.py`
  model provider layer loaded from repo-local `benchmark/ctfmix/models_config.yaml`

## Runtime Flow

### RL / SkyRL path

`main_training.py`
-> SkyRL generator loads parquet rows
-> creates `vulrl.SecurityEnv`
-> `SecurityEnv.__init__` creates `CTFMixAdapter` and calls `setup()`
-> `CTFMixAdapter.setup()` creates `CTFMixRuntime` and prepares the long-lived agent container
-> `SecurityEnv.init(prompt)` triggers `reset()`
-> `runtime.reset()` starts compose if needed, validates server, copies manifest files, installs commands, builds initial observation
-> each `step()` executes one command
-> final reward is only given on episode end from submit/flag validation

### Standalone path

`infra/ctfmix_run.py`
-> `vulrl.ctfmix.standalone`
-> either scripted commands or `Agent.run()`
-> same `CTFMixRuntime`
-> same command set, same compose/network logic, same submit validation

## Reward Logic

`ctfmix` does not use the Vulhub BLEU reward path.

Current behavior:

- intermediate steps: reward `0.0`
- terminal correct submit: reward `1.0`
- terminal wrong submit / failure: reward `0.0`

Main implementation:

- `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/ctfmix/runtime.py`
- `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/env/security_env.py`

`SecurityEnv` prefers the adapter/runtime terminal reward at episode end.

## Benchmark and Config Layout

Repo-local benchmark root:

- `/VulRL/benchmark/ctfmix`

Families currently included:

- `cybench`
- `intercode_ctf`
- `nyu_ctf`

Prompt/config bundle:

- `/VulRL/benchmark/ctfmix/config/default_ctf.yaml`
- `/VulRL/benchmark/ctfmix/config/commands/*`
- `/VulRL/benchmark/ctfmix/models_config.yaml`

Important behavior:

- challenge files exposed to the agent are manifest-based
- runtime copies only `challenge.json["files"]` style entries
- it does not blindly copy the full challenge directory anymore
- `docker-compose.yml` is used for challenge startup, not copied as agent repo content unless listed in the manifest

## Key Entry Points

### 1. Dataset conversion

File:

- `/VulRL/dataset/dataset_converter.py`

Command:

```bash
cd /VulRL
/VulRL/venv/bin/python \
  dataset/dataset_converter.py ctf-skyrl \
  --input /VulRL/benchmark/ctfmix \
  --output /VulRL/infra/outputs/ctfmix_all_benchmarks.parquet
```

Output schema is the SkyRL 7-column format:

- `prompt`
- `env_class`
- `env_config`
- `poc_info`
- `tools`
- `task_id`
- `metadata`

### 2. Standalone agent run

Command:

```bash
/VulRL/venv/bin/python \
  /VulRL/infra/ctfmix_run.py \
  --challenge-dir /VulRL/benchmark/ctfmix/cybench/GLA/web/GlacierExchange \
  --model-name gpt-4.1 \
  --step-limit 20 \
  --traj-dir /VulRL/infra/outputs/ctfmix_agent
```

### 3. Batch standalone smoke runs

File:

- `/VulRL/infra/run_ctfmix_batch_standalone.py`

Command:

```bash
/VulRL/venv/bin/python \
  /VulRL/infra/run_ctfmix_batch_standalone.py \
  --model-name gpt-4.1-nano \
  --step-limit 3
```

### 4. SkyRL training entry

File:

- `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/main_training.py`

Minimal smoke command used for wiring checks:

```bash
cd /VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl

export HF_HOME="$HOME/.cache/huggingface"
export TRANSFORMERS_CACHE="$HOME/.cache/huggingface/hub"
export PYTHONPATH="/VulRL/SkyRL/skyrl-train:/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl:/VulRL/SkyRL/skyrl-gym:$PYTHONPATH"

/VulRL/venv/bin/python \
  /VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/main_training.py \
  ++data.train_data="['/VulRL/infra/outputs/ctfmix_all_benchmarks.parquet']" \
  ++data.val_data=null \
  ++trainer.epochs=1 \
  ++trainer.train_batch_size=1 \
  ++trainer.policy_mini_batch_size=1 \
  ++trainer.critic_mini_batch_size=1 \
  ++trainer.micro_train_batch_size_per_gpu=1 \
  ++trainer.micro_forward_batch_size_per_gpu=1 \
  ++trainer.eval_before_train=false \
  ++trainer.eval_interval=-1 \
  ++trainer.max_prompt_length=2048 \
  ++trainer.project_name=ctfmix \
  ++trainer.run_name=ctfmix-smoke \
  ++trainer.logger=console \
  ++trainer.policy.model.path='Qwen/Qwen2.5-3B-Instruct' \
  ++generator.model_name='Qwen/Qwen2.5-3B-Instruct' \
  ++generator.n_samples_per_prompt=1 \
  ++generator.max_turns=1
```

## Frequently Changed Arguments

### Standalone

From `ctfmix_run.py` / `standalone.py`:

- `--task`
- `--challenge-dir`
- `--bench-root`
- `--variant`
- `--commands`
- `--model-name`
- `--step-limit`
- `--traj-dir`
- `--temperature`
- `--top-p`
- `--top-k`

### Batch smoke

From `run_ctfmix_batch_standalone.py`:

- `--audit`
- `--results`
- `--traj-dir`
- `--model-name`
- `--step-limit`
- `--family`
- `--limit`

### Converter

From `dataset_converter.py ctf-skyrl`:

- `--input`
- `--output`
- `--variant`

### Runtime task fields commonly overridden in task YAML

- `task_id`
- `name`
- `description`
- `category`
- `flag_format`
- `flag` / `flag_sha256` / `flag_check`
- `compose_path`
- `repo_path`
- `files`
- `server_description`
- `box`
- `internal_port`
- `target_protocol`
- `command_config`
- `image_name`
- `enable_dynamic_ports`
- `exclude_paths`
- `hide_solution_artifacts`
- `expose_flag_to_agent`

## Important Dependencies

Runtime expects:

- Docker / Docker Compose
- the agent image, usually `sweagent/enigma:latest`
- Python deps from the inner repo venv

Prompt/config/model defaults are loaded from:

- `/VulRL/benchmark/ctfmix/config/default_ctf.yaml`
- `/VulRL/benchmark/ctfmix/models_config.yaml`

## Notes on Current Known Limits

- Some benchmark challenges fail for reasons outside the integration layer, mainly stale Docker images or obsolete Debian `buster` apt repositories.


## Recommended First Files for a New Maintainer

Read in this order:

1. `/VulRL/README_CTFMIX.md`
2. `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/ctfmix/runtime.py`
3. `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/docker1/adapters/ctfmix_adapter.py`
4. `/VulRL/SkyRL/skyrl-train/vulrl_inside_skyrl/vulrl/env/security_env.py`
5. `/VulRL/dataset/dataset_converter.py`
6. `/VulRL/benchmark/ctfmix/config/default_ctf.yaml`

That sequence covers the data path, the environment path, and the standalone path with minimal context switching.
