"""
EzVulRL Generator - HTTP-based generator for VulRL.

This generator inherits from SkyRLGymGenerator but delegates rollout execution
to a Worker Router API instead of running locally. It mimics the mini_swe_agent
pattern but uses HTTP communication.
"""

import asyncio
from typing import Dict, List, Optional, Any, Tuple, Union
from pathlib import Path
import sys

# Add SkyRL to path
skyrl_path = Path(__file__).parent.parent.parent / "SkyRL" / "skyrl-train"
sys.path.insert(0, str(skyrl_path))

from omegaconf import DictConfig
from skyrl_train.config import GeneratorConfig, SkyRLGymConfig
from skyrl_train.generators.skyrl_gym_generator import SkyRLGymGenerator, GeneratorOutput, GeneratorInput
from skyrl_train.generators.base import TrajectoryID, TrainingPhase, BatchMetadata
from skyrl_train.inference_engines.base import ConversationType
from skyrl_train.inference_engines.inference_engine_client import InferenceEngineClient
from skyrl_train.inference_engines.utils import get_sampling_params_for_backend
from skyrl_train.generators.utils import (
    get_rollout_metrics,
    get_response_ids_and_loss_mask_from_messages,
)

from .worker_router_client import WorkerRouterClient

# Add worker_router to path for model imports
sys.path.insert(0, str(Path(__file__).parent.parent / "worker_router"))
from worker_router.models import RolloutRequest, TrajectoryStep


class EzVulRLGenerator(SkyRLGymGenerator):
    """
    Generator that delegates VulRL rollouts to Worker Router API.
    
    Similar to mini_swe_agent pattern, but instead of using Ray remote actors,
    this submits rollout requests via HTTP and polls for results.
    
    Flow:
    1. SkyRL calls generate() with batch of prompts
    2. For each prompt, call vulrl_agent_loop()
    3. vulrl_agent_loop() submits HTTP request to Worker Router
    4. Active polling loop waits for Worker Unit to complete task
    5. Convert result trajectory to SkyRL format and return
    """
    
    def __init__(
        self,
        generator_cfg: Union[GeneratorConfig, DictConfig],
        skyrl_gym_cfg: Union[SkyRLGymConfig, DictConfig],
        inference_engine_client: InferenceEngineClient,  # Will be IGNORED
        tokenizer,
        model_name: str,
        worker_router_url: str = "http://localhost:5000",
        llm_endpoint: str = "http://localhost:8001",
        llm_model_name: str = "qwen2.5-1.5b",
        polling_config: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize the generator.
        
        Args:
            generator_cfg: Generator configuration from SkyRL
            skyrl_gym_cfg: SkyRL Gym configuration
            inference_engine_client: InferenceEngineClient (IGNORED - we use ez_llm_server)
            tokenizer: Tokenizer for converting text to token IDs
            model_name: Model name for logging
            worker_router_url: URL of the Worker Router API
            llm_endpoint: URL of the LLM server (ez_llm_server)
            llm_model_name: Model name served by LLM server
            polling_config: Polling configuration (timeout, interval, etc.)
        """
        # Call parent constructor
        super().__init__(generator_cfg, skyrl_gym_cfg, inference_engine_client, tokenizer, model_name)
        
        # Worker Router configuration
        self.worker_router_url = worker_router_url
        self.llm_endpoint = llm_endpoint
        self.llm_model_name = llm_model_name
        
        # Polling configuration
        self.polling_config = polling_config or {
            "timeout": 600.0,        # 10 minutes max per rollout
            "poll_interval": 10.0,   # Check status every 10 seconds
            "verbose": True,         # Print polling progress
        }
        
        # Initialize Worker Router client
        self.worker_router_client = WorkerRouterClient(worker_router_url)
        
        # Store config for later use
        self.generator_cfg = generator_cfg
        self.tokenizer = tokenizer
        self.model_name = model_name
        
        print(f"[EzVulRLGenerator] Initialized")
        print(f"  Worker Router: {self.worker_router_url}")
        print(f"  LLM Endpoint: {self.llm_endpoint}")
        print(f"  LLM Model: {self.llm_model_name}")
        print(f"  Polling: timeout={self.polling_config['timeout']}s, interval={self.polling_config['poll_interval']}s")
    
    async def vulrl_agent_loop(
        self,
        prompt: ConversationType,
        env_extras: Dict[str, Any],
        max_tokens: int,
        max_input_length: int,
        sampling_params: Dict[str, Any],
        trajectory_id: TrajectoryID,
        batch_metadata: BatchMetadata,
    ) -> Tuple[Optional[List[int]], Optional[float], Optional[str], Optional[List[int]], Optional[List[int]], Optional[List[int]]]:
        """
        Main agent loop - delegates to Worker Router instead of running locally.
        
        Args:
            prompt: Initial prompt (ConversationType = List[Dict] or str)
            env_extras: Environment extras (CVE info, vulhub path, etc.)
            max_tokens: Maximum tokens to generate
            max_input_length: Maximum input length
            sampling_params: Sampling parameters (temperature, etc.)
            trajectory_id: Unique trajectory ID
            batch_metadata: Batch metadata (global_step, training_phase, etc.)
            
        Returns:
            Tuple of (response_ids, reward, stop_reason, loss_mask, prompt_ids, rollout_logprobs)
            Returns (None, None, None, None, None, None) on failure
        """
        try:
            # Extract prompt text
            if isinstance(prompt, list):
                # ConversationType is list of messages
                prompt_text = prompt[-1].get("content", "") if prompt else ""
            elif isinstance(prompt, str):
                prompt_text = prompt
            else:
                prompt_text = str(prompt)
            
            # Build RolloutRequest
            request = RolloutRequest(
                cve_id=env_extras.get("cve_id", "UNKNOWN"),
                vulhub_path=env_extras.get("vulhub_path", ""),
                prompt=prompt_text,
                llm_endpoint=self.llm_endpoint,
                model_name=self.llm_model_name,
                max_steps=env_extras.get("max_steps", 10),
                temperature=sampling_params.get("temperature", 0.7),
                max_tokens=max_tokens,
                timeout=int(self.polling_config["timeout"]),
                metadata={
                    "trajectory_id": str(trajectory_id),
                    "global_step": batch_metadata.global_step,
                    "training_phase": batch_metadata.training_phase,
                },
            )
            
            print(f"[EzVulRLGenerator] Submitting rollout: {request.cve_id}")
            
            # Submit to Worker Router
            task_id = await self.worker_router_client.submit_rollout(request)
            print(f"[EzVulRLGenerator] Task ID: {task_id}")
            
            # Wait for completion (active polling loop)
            result = await self.worker_router_client.wait_for_rollout(
                task_id,
                timeout=self.polling_config["timeout"],
                poll_interval=self.polling_config["poll_interval"],
                verbose=self.polling_config["verbose"],
            )
            
            print(f"[EzVulRLGenerator] Received result: reward={result.reward}, steps={len(result.trajectory or [])}")
            
            # Convert trajectory to SkyRL message format
            messages = self._convert_trajectory_to_messages(result.trajectory or [], prompt)
            
            if not messages:
                print(f"[EzVulRLGenerator] ⚠ No messages in trajectory, skipping")
                return None, None, None, None, None, None
            
            # Tokenize messages (same as mini_swe_generator)
            initial_input_ids = self.tokenizer.apply_chat_template(
                messages[:2] if len(messages) >= 2 else messages,
                add_generation_prompt=False,
                tokenize=True
            )
            initial_prompt_length = len(initial_input_ids)
            
            # Get response messages (skip initial prompt)
            response_messages = messages[2:] if len(messages) > 2 else []
            
            if not response_messages:
                print(f"[EzVulRLGenerator] ⚠ No response messages, skipping")
                return None, None, None, None, None, None
            
            # Tokenize full conversation
            all_input_ids = self.tokenizer.apply_chat_template(
                messages,
                add_generation_prompt=False,
                tokenize=True
            )
            
            # Response IDs = everything after initial prompt
            response_ids = all_input_ids[initial_prompt_length:]
            
            # Loss mask: 1 for assistant tokens, 0 for user tokens
            loss_mask = self._get_loss_mask(response_messages)
            
            # Ensure lengths match
            if len(response_ids) != len(loss_mask):
                # Truncate to shorter length
                min_len = min(len(response_ids), len(loss_mask))
                response_ids = response_ids[:min_len]
                loss_mask = loss_mask[:min_len]
            
            reward = result.reward or 0.0
            stop_reason = "completed" if result.success else "failed"
            
            # Truncate to max response tokens
            max_response_tokens = max_tokens
            response_ids = response_ids[:max_response_tokens]
            loss_mask = loss_mask[:max_response_tokens]
            
            return (response_ids, reward, stop_reason, loss_mask, initial_input_ids, None)
            
        except Exception as e:
            print(f"[EzVulRLGenerator] ✗ Error in vulrl_agent_loop: {e}")
            import traceback
            traceback.print_exc()
            return None, None, None, None, None, None
    
    def _convert_trajectory_to_messages(
        self,
        trajectory: List[TrajectoryStep],
        initial_prompt: ConversationType,
    ) -> List[Dict[str, str]]:
        """
        Convert worker trajectory to SkyRL message format.
        
        Worker format:
            TrajectoryStep(action, observation, reward, done)
        
        SkyRL format:
            [
                {"role": "system", "content": "..."},
                {"role": "user", "content": "..."},
                {"role": "assistant", "content": "..."},
                {"role": "user", "content": "..."},
                ...
            ]
        
        Args:
            trajectory: List of TrajectoryStep from worker
            initial_prompt: Initial prompt from SkyRL
            
        Returns:
            List of message dicts in SkyRL format
        """
        messages = []
        
        # Add initial system message
        messages.append({
            "role": "system",
            "content": "You are a penetration testing agent. Provide concrete bash commands."
        })
        
        # Add initial user prompt
        if isinstance(initial_prompt, list):
            # Extract user message from list
            for msg in initial_prompt:
                if msg.get("role") in ("user", "system"):
                    messages.append(msg)
        elif isinstance(initial_prompt, str):
            messages.append({
                "role": "user",
                "content": initial_prompt
            })
        
        # Convert trajectory steps to alternating assistant/user messages
        for step in trajectory:
            # Assistant action
            messages.append({
                "role": "assistant",
                "content": step.action
            })
            # User observation
            messages.append({
                "role": "user",
                "content": step.observation
            })
        
        return messages
    
    def _get_loss_mask(self, messages: List[Dict[str, str]]) -> List[int]:
        """
        Generate loss mask for messages.
        
        Loss mask: 1 for assistant tokens (train on these), 0 for user tokens (ignore).
        
        Args:
            messages: List of message dicts
            
        Returns:
            List of 0/1 indicating which tokens to include in loss
        """
        loss_mask = []
        
        for msg in messages:
            # Tokenize this message
            msg_ids = self.tokenizer.encode(msg["content"], add_special_tokens=False)
            
            # Mask: 1 for assistant, 0 for user
            if msg["role"] == "assistant":
                loss_mask.extend([1] * len(msg_ids))
            else:
                loss_mask.extend([0] * len(msg_ids))
        
        return loss_mask
    
    async def generate(self, input_batch: GeneratorInput) -> GeneratorOutput:
        """
        Generate trajectories for the input batch.
        
        This is called by SkyRL's training loop. We delegate to vulrl_agent_loop()
        for each prompt in the batch.
        
        Args:
            input_batch: GeneratorInput with prompts, env_extras, etc.
            
        Returns:
            GeneratorOutput with response_ids, rewards, loss_masks, etc.
        """
        prompts = input_batch["prompts"]
        env_extras = input_batch["env_extras"]
        trajectory_ids = input_batch["trajectory_ids"]
        batch_metadata = input_batch["batch_metadata"]
        max_tokens = self.generator_cfg.sampling_params.max_generate_length
        max_input_length = self.generator_cfg.max_input_length
        sampling_params = get_sampling_params_for_backend(
            self.generator_cfg.backend, self.generator_cfg.sampling_params
        )
        
        print(f"[EzVulRLGenerator] Generating batch of {len(prompts)} trajectories")
        
        # Create tasks for parallel execution
        tasks = []
        for i in range(len(prompts)):
            tasks.append(
                self.vulrl_agent_loop(
                    prompts[i],
                    env_extras[i],
                    max_tokens=max_tokens,
                    max_input_length=max_input_length,
                    sampling_params=sampling_params,
                    trajectory_id=trajectory_ids[i],
                    batch_metadata=batch_metadata,
                )
            )
        
        # Execute all tasks in parallel
        all_outputs = await asyncio.gather(*tasks)
        
        # Filter out None entries (failed trajectories)
        responses = [output[0] for output in all_outputs if output[0] is not None]
        rewards = [output[1] for output in all_outputs if output[0] is not None]
        stop_reasons = [output[2] for output in all_outputs if output[0] is not None]
        loss_masks = [output[3] for output in all_outputs if output[0] is not None]
        prompt_token_ids = [output[4] for output in all_outputs if output[0] is not None]
        
        if not responses:
            raise ValueError(
                "Found no valid responses for this step. This means that generation "
                "failed for all trajectories, likely due to Worker Router issues."
            )
        
        print(f"[EzVulRLGenerator] Generated {len(responses)}/{len(prompts)} valid trajectories")
        
        # Calculate rollout metrics
        rollout_metrics = get_rollout_metrics(responses, rewards)
        
        generator_output: GeneratorOutput = {
            "prompt_token_ids": prompt_token_ids,
            "response_ids": responses,
            "rewards": rewards,
            "loss_masks": loss_masks,
            "stop_reasons": stop_reasons,
            "rollout_metrics": rollout_metrics,
            "rollout_logprobs": None,
        }
        
        return generator_output
    
    async def cleanup(self):
        """Cleanup resources."""
        await self.worker_router_client.close()
