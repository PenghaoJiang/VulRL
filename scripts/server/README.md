# Server Runbook

These scripts assume:

- Worker Router runs on the same machine as training.
- Worker Router stays on `http://127.0.0.1:12345`.
- The training parquet is built from `nyu_ctf_subtask` and `cybench`.

## 1. Setup

```bash
cd /path/to/VulRL
bash worker_orchestrator/setup.sh
```

## 2. Convert training data

```bash
cd /path/to/VulRL
bash scripts/server/convert_ctf_subtask_data.sh
```

Default parquet:

`dataset/ctf_parquet/train_ctf_subtask_combined.parquet`

## 3. Start Worker Router

```bash
cd /path/to/VulRL
bash scripts/server/start_worker_router_logged.sh
```

## 4. Launch training

```bash
cd /path/to/VulRL
bash scripts/server/run_ctf_rl_training.sh
```

## 4b. Launch one-case fake-train smoke test

```bash
cd /path/to/VulRL
bash scripts/server/run_train_ctf_fake_test.sh
```

## 5. Stop Worker Router

```bash
cd /path/to/VulRL
bash scripts/server/stop_worker_router_logged.sh
```

## Logs

- Conversion log: `logs/server/convert_latest.log`
- Fake-train conversion log: `logs/server/convert_fake_train_<run_name>.log`
- Training log: `logs/server/train_latest.log`
- Router stdout/stderr: `logs/server/worker_router_stdout_latest.log`
- Router app log: `worker_orchestrator/logs/worker_router.log`
- Worker process logs: `worker_orchestrator/logs/worker_auto_*.log`

## Training outputs

- Checkpoints: `outputs/checkpoints/<run_name>/`
- Hydra output dir: `outputs/skyrl/<run_name>/`

The training script also prints the exact `run_name`, checkpoint path, and Hydra output path at startup.
