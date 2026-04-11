"""
Execute a complete VulRL rollout (episode).
Self-contained - no imports from SkyRL folders.

Updated to support pluggable agents (DemoAgent, CTFAgent).
"""

import time
from pathlib import Path
from typing import Dict, Any, List, Optional

# Import from worker_orchestrator modules only
from worker_router.models import RolloutRequest, RolloutResult
from ez_llm_server.client import InferenceEngineClientWrapper

# Import from worker_unit modules (copied from vulrl_inside_skyrl)
from worker_unit.env import SecurityEnv
from worker_unit.reward import RewardCalculator
# from worker_unit.agent_loop import agent_loop  # OLD: Commented out, using agents instead

from worker_unit.agent.demo_agent import DemoAgent
from worker_unit.agent.ctf_agent import CTFAgent


def _trajectory_to_dicts(trajectory) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for step in trajectory:
        if hasattr(step, "model_dump"):
            rows.append(step.model_dump())
        elif hasattr(step, "dict"):
            rows.append(step.dict())
        else:
            rows.append(dict(step))
    return rows


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_DEFAULT_CVEBENCH_ROOT = _REPO_ROOT / "benchmark" / "cve-bench"
_DEFAULT_CTFMIX_ROOT = _REPO_ROOT / "benchmark" / "ctfmix"
_DEFAULT_VULHUB_BENCHMARK_ROOT = _REPO_ROOT / "benchmark" / "vulhub"


class RolloutExecutor:
    """Execute a complete VulRL rollout."""
    
    def __init__(self):
        # Reward calculator will be initialized per-request with task-specific config
        # TODO: However, current structure assumes worker unit and skyrl share the same machine, 
        #       leading to potential issues when running on different machines (using the same file path of the parquet). 
        pass
    
    async def execute(
        self,
        request: RolloutRequest,
        agent_type: str = "ctf"
    ) -> RolloutResult:
        """
        Execute a complete rollout with specified agent.
        
        Args:
            request: RolloutRequest with CVE, prompt, LLM config
            agent_type: Type of agent to use ("demo" or "ctf")
                - "demo": Simple bash command agent (original agent_loop logic)
                - "ctf": Advanced CTFMix agent with thought/action parsing (default)
            
        Returns:
            RolloutResult with trajectory and rewards
        """
        task_id = f"{request.cve_id}_{int(time.time())}"
        start_time = time.time()
        
        print(f"\n{'='*70}")
        print(f"Starting Rollout: {task_id}")
        print(f"{'='*70}")
        task_type = (request.metadata.get("task_type") or "vulhub").lower()
        print(f"CVE: {request.cve_id}")
        print(f"Task type: {task_type}")
        print(f"Vulhub Path: {request.vulhub_path}")
        print(f"Prompt: {request.prompt}")
        print(f"Max Steps: {request.max_steps}")
        print()
        
        env = None

        try:
            # 1. Initialize LLM client
            print("[RolloutExecutor] Initializing LLM client...")
            llm_client = InferenceEngineClientWrapper(
                endpoint=request.llm_endpoint,
                model_name=request.model_name,
            )
            print(f"[RolloutExecutor] LLM client ready: {request.llm_endpoint}")

            # 2. Initialize environment
            print("[RolloutExecutor] Initializing environment...")

            if task_type == "cvebench":
                cvebench_root = request.metadata.get("cvebench_root") or str(_DEFAULT_CVEBENCH_ROOT)
                env_config = {
                    "task_type": "cvebench",
                    "task_id": request.cve_id,
                    "cve_id": request.cve_id,
                    "cvebench_root": cvebench_root,
                    "cvebench_version": request.metadata.get("cvebench_version", "critical"),
                    "cvebench_tag": request.metadata.get("cvebench_tag"),
                    "max_steps": request.max_steps,
                    "timeout": request.metadata.get("timeout", 30),
                    "backend_config": {"cvebench_root": cvebench_root},
                }
            elif task_type in ("nyu_ctf", "cybench_docker"):
                ctfmix_root = request.metadata.get("ctfmix_root") or str(
                    _DEFAULT_CTFMIX_ROOT
                )
                challenge_rel = (
                    request.metadata.get("challenge_relative_path")
                    or request.vulhub_path
                    or ""
                ).strip().replace("\\", "/").strip("/")
                env_config = {
                    "task_type": task_type,
                    "task_id": request.cve_id,
                    "max_steps": request.max_steps,
                    "timeout": request.metadata.get("timeout", 30),
                    "ctfmix_root": ctfmix_root,
                    "challenge_relative_path": challenge_rel,
                    "backend_config": {
                        "ctfmix_root": ctfmix_root,
                        "challenge_relative_path": challenge_rel,
                    },
                }
            else:
                # Prefer metadata; if missing or not a directory on this host (e.g. stale
                # parquet paths from another machine), use this checkout's benchmark/vulhub.
                _meta_vb = request.metadata.get("vulhub_base_path")
                if _meta_vb and Path(_meta_vb).is_dir():
                    vulhub_base_path = str(Path(_meta_vb).resolve())
                else:
                    if _meta_vb:
                        print(
                            f"[RolloutExecutor] vulhub_base_path not found on host ({_meta_vb!r}), "
                            f"using {_DEFAULT_VULHUB_BENCHMARK_ROOT}"
                        )
                    vulhub_base_path = str(_DEFAULT_VULHUB_BENCHMARK_ROOT.resolve())
                env_config = {
                    "task_type": "vulhub",
                    "task_id": request.cve_id,
                    "vulhub_path": request.vulhub_path,
                    "max_steps": request.max_steps,
                    "backend_config": {
                        "vulhub_path": request.vulhub_path,
                        "vulhub_base_path": vulhub_base_path,
                    },
                    "target_host": "target",
                    "target_port": 80,
                    "target_protocol": "http",
                    "timeout": 30,
                }

            env = SecurityEnv(config=env_config)
            print("[RolloutExecutor] Environment ready")
            
            # 3. Reset environment
            print("[RolloutExecutor] Resetting environment...")
            observation, info = env.reset()
            
            # Convert observation to string
            if hasattr(observation, 'to_text'):
                observation_str = observation.to_text()
            elif hasattr(observation, 'text'):
                observation_str = observation.text
            else:
                observation_str = str(observation)
            
            print(f"[RolloutExecutor] Initial observation: {observation_str[:200]}...")
            
            # 4. Create and run agent
            print(f"[RolloutExecutor] Creating agent (type: {agent_type})...")

            if agent_type == "demo":
                agent = DemoAgent(
                    env=env,
                    llm_client=llm_client,
                    config={
                        "model_name": request.model_name,
                        "temperature": request.temperature,
                        "max_tokens": request.max_tokens,
                    },
                )
            elif agent_type == "ctf":
                agent = CTFAgent(
                    env=env.adapter,
                    llm_client=llm_client,
                    config={
                        "model_name": request.model_name,
                        "temperature": request.temperature,
                        "max_tokens": request.max_tokens,
                        "step_limit": request.max_steps,
                        "config_file": request.metadata.get("agent_config_file"),
                    },
                )
            else:
                raise ValueError(f"Unknown agent_type: {agent_type}")

            print(f"[RolloutExecutor] Starting {agent.get_name()}...")
            trajectory = await agent.run(
                initial_prompt=request.prompt,
                max_steps=request.max_steps,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            print(f"[RolloutExecutor] Agent completed: {len(trajectory)} steps")

            traj_dicts = _trajectory_to_dicts(trajectory)

            # 5–6. Reward, then teardown for cvebench (needs live /done); vulhub closes first (offline BLEU)
            print("[RolloutExecutor] Computing rewards...")
            if task_type == "cvebench":
                reward_config = {
                    "attacker_container_name": getattr(
                        env.adapter, "attacker_container_name", None
                    ),
                    "evaluator_done_url": getattr(
                        env.adapter,
                        "evaluator_done_url",
                        "http://target:9091/done",
                    ),
                }
                reward_calculator = RewardCalculator(
                    task_type="cvebench",
                    config=reward_config,
                )
                reward_task_id = request.cve_id
                total_reward = reward_calculator.compute_episode_reward(
                    trajectory=traj_dicts,
                    task_id=reward_task_id,
                )
                print(f"[RolloutExecutor] Total reward: {total_reward}")
                if env:
                    env.close()
                    print("[RolloutExecutor] Environment closed")
            else:
                if env:
                    env.close()
                    print("[RolloutExecutor] Environment closed")
                if task_type in ("nyu_ctf", "cybench_docker"):
                    reward_config = {
                        "expected_flag": getattr(
                            env.adapter, "expected_flag", None
                        ),
                        "ctfmix_supported": getattr(
                            env.adapter, "ctfmix_supported", True
                        ),
                        "flag_format": request.metadata.get(
                            "flag_format", "flag{...}"
                        ),
                    }
                    reward_calculator = RewardCalculator(
                        task_type=task_type,
                        config=reward_config,
                    )
                    reward_task_id = (
                        request.metadata.get("challenge_relative_path")
                        or request.vulhub_path
                        or request.cve_id
                    )
                else:
                    reward_config = {
                        "dataset_path": request.metadata.get("dataset_path", ""),
                    }
                    reward_calculator = RewardCalculator(
                        task_type="vulhub",
                        config=reward_config,
                    )
                    reward_task_id = request.vulhub_path or request.cve_id
                total_reward = reward_calculator.compute_episode_reward(
                    trajectory=traj_dicts,
                    task_id=reward_task_id,
                )
                print(f"[RolloutExecutor] Total reward: {total_reward}")
            
            # 7. Build result
            duration = time.time() - start_time
            success = total_reward > 0.5  # TODO: Define success criteria
            
            print(f"\n{'='*70}")
            print(f"Rollout Completed Successfully")
            print(f"{'='*70}")
            print(f"Duration: {duration:.2f}s")
            print(f"Steps: {len(trajectory)}")
            print(f"Reward: {total_reward}")
            print(f"Success: {success}")
            print()
            
            return RolloutResult(
                task_id=task_id,
                status="completed",
                worker_id=None,  # Set by main.py
                queued_at=start_time,
                started_at=start_time,
                completed_at=time.time(),
                duration=duration,
                reward=total_reward,
                trajectory=trajectory,
                success=success,
                metadata=request.metadata,
                error=None,
                error_type=None
            )
            
        except Exception as e:
            # Cleanup on error
            if env:
                try:
                    env.close()
                except:
                    pass
            
            duration = time.time() - start_time
            
            print(f"\n{'='*70}")
            print(f"Rollout Failed")
            print(f"{'='*70}")
            print(f"Error: {str(e)}")
            print(f"Duration: {duration:.2f}s")
            print()
            
            import traceback
            traceback.print_exc()
            
            return RolloutResult(
                task_id=task_id,
                status="failed",
                worker_id=None,
                queued_at=start_time,
                started_at=start_time,
                completed_at=time.time(),
                duration=duration,
                reward=None,
                trajectory=None,
                success=False,
                metadata=request.metadata,
                error=str(e),
                error_type=type(e).__name__
            )
