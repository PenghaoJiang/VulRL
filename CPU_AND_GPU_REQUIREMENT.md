# SkyRL CPU and GPU Requirements (Worker Router Separate)

This document estimates hardware for the **SkyRL machine only** when rollout execution (Worker Router + worker units) runs on a separate host.

## Scope

Included on this machine:
- Policy training process (`trainer.strategy=fsdp2`)
- Reference model for KL (`trainer.algorithm.use_kl_loss=true`)
- Local vLLM inference engine (`generator.run_engines_locally=True`, HTTP endpoint enabled)
- Ray/Python runtime and dataloader overhead

Excluded from this machine:
- Worker Router and worker unit containers
- Remote attack environments and their model serving

## Model names (Hugging Face)

- `Qwen/Qwen2.5-0.5B-Instruct`
- `Qwen/Qwen2.5-1.5B-Instruct`
- `Qwen/Qwen2.5-3B-Instruct`
- `Qwen/Qwen2.5-7B-Instruct`
- `Qwen/Qwen2.5-14B-Instruct`
- `Qwen/Qwen2.5-32B-Instruct`
- `Qwen/Qwen2.5-72B-Instruct`

## Assumptions used for planning

- Weights in bf16/fp16: ~`2 bytes/param`.
- GPU memory (SkyRL training stack total): rough baseline ~`18-22 bytes/param` across all GPUs.
- Host RAM (SkyRL-only, with policy + ref + local vLLM process overlap): rough baseline ~`3x-5x` bf16 weight size.
- Recommended purchase/provision target: add **30-50% buffer** to baseline.

## GPU requirements (SkyRL machine only)

| Model         | Params | BF16 weights | GPU baseline (total) | GPU with 30-50% buffer |
|---------------|-------:|-------------:|---------------------:|-----------------------:|
| Qwen2.5-0.5B  |   0.5B |        ~1 GB |             ~9-11 GB |              ~12-17 GB |
| Qwen2.5-1.5B  |   1.5B |        ~3 GB |            ~27-33 GB |              ~36-50 GB |
| Qwen2.5-3B    |     3B |        ~6 GB |            ~54-66 GB |              ~71-99 GB |
| Qwen2.5-7B    |     7B |       ~14 GB |          ~126-154 GB |            ~164-231 GB |
| Qwen2.5-14B   |    14B |       ~28 GB |          ~252-308 GB |            ~328-462 GB |
| Qwen2.5-32B   |    32B |       ~64 GB |          ~576-704 GB |           ~749-1056 GB |
| Qwen2.5-72B   |    72B |      ~144 GB |        ~1296-1584 GB |          ~1685-2376 GB |

## RAM requirements (SkyRL machine only)

| Model         | Params | BF16 weights | RAM baseline | RAM with 30-50% buffer |
|---------------|-------:|-------------:|-------------:|-----------------------:|
| Qwen2.5-0.5B  |   0.5B |        ~1 GB |      ~3-5 GB |                ~4-8 GB |
| Qwen2.5-1.5B  |   1.5B |        ~3 GB |     ~9-15 GB |              ~12-23 GB |
| Qwen2.5-3B    |     3B |        ~6 GB |    ~18-30 GB |              ~24-45 GB |
| Qwen2.5-7B    |     7B |       ~14 GB |    ~42-70 GB |             ~55-105 GB |
| Qwen2.5-14B   |    14B |       ~28 GB |   ~84-140 GB |            ~110-210 GB |
| Qwen2.5-32B   |    32B |       ~64 GB |  ~192-320 GB |            ~250-480 GB |
| Qwen2.5-72B   |    72B |      ~144 GB |  ~432-720 GB |           ~562-1080 GB |

## Storage requirements for checkpoints

Assuming:
- `trainer.ckpt_interval=10`
- `500` generations (roughly `500` global steps)
- checkpoints kept = `500 / 10 = 50`
- `trainer.max_ckpts_to_keep=-1` (keep all)
- GRPO-like run where policy checkpoint is dominant

Per-checkpoint size planning rule:
- rough baseline: `~2x-4x` BF16 model weight size
- then add **30-50%** buffer for filesystem overhead and run variance

| Model         | BF16 weights | Per-ckpt baseline (`~2x-4x`) | For 50 ckpts baseline | For 50 ckpts + 30-50% buffer |
|---------------|-------------:|-----------------------------:|----------------------:|-----------------------------:|
| Qwen2.5-0.5B  |       ~1 GB  |                      ~2-4 GB |           ~100-200 GB |                  ~130-300 GB |
| Qwen2.5-1.5B  |       ~3 GB  |                     ~6-12 GB |           ~300-600 GB |                  ~390-900 GB |
| Qwen2.5-3B    |       ~6 GB  |                    ~12-24 GB |          ~600-1200 GB |                 ~780-1800 GB |
| Qwen2.5-7B    |      ~14 GB  |                    ~28-56 GB |         ~1400-2800 GB |                ~1820-4200 GB |
| Qwen2.5-14B   |      ~28 GB  |                   ~56-112 GB |         ~2800-5600 GB |                ~3640-8400 GB |
| Qwen2.5-32B   |      ~64 GB  |                  ~128-256 GB |        ~6400-12800 GB |               ~8320-19200 GB |
| Qwen2.5-72B   |     ~144 GB  |                  ~288-576 GB |       ~14400-28800 GB |              ~18720-43200 GB |

Notes:
- `trainer.dump_data_batch=true` can add significant extra disk usage over long runs.
- If disk is tight, either increase `trainer.ckpt_interval` or set a finite `trainer.max_ckpts_to_keep`.

## CPU requirements and constraints

CPU is usually not the main bottleneck for GPU training, but there are practical limits:

| Workload size | Recommended CPU (SkyRL machine) | Notes |
|---|---|---|
| 0.5B-1.5B | 8-16 vCPU | Sufficient for Python/Ray/runtime overhead and moderate I/O |
| 3B-7B | 16-32 vCPU | Better for checkpoint save/load and avoiding dataloader stalls |
| 14B+ | 32+ vCPU | Recommended when using many GPUs and frequent checkpointing |

Additional CPU guidance:
- Prefer high single-core performance for orchestration-heavy phases.
- Keep at least a few free CPU cores during checkpoint save windows.
- Fast local NVMe is strongly recommended; slow disks make CPU wait and inflate step time.

## Practical reading

- These are **planning estimates**, not strict lower bounds.
- With your launch style, single-GPU is usually practical for `0.5B` and `1.5B`; `3B` may work only with aggressive settings and careful tuning.
- `7B+` generally requires multi-GPU sharding.
- Longer contexts and larger generation lengths increase activation and KV-cache pressure beyond these rough numbers.

## Reference

- Qwen org page: [https://huggingface.co/Qwen/models](https://huggingface.co/Qwen/models)
