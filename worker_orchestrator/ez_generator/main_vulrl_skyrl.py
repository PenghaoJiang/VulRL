"""
VulRL PPO Training Entry Point for SkyRL

This module provides the main entry point for training VulRL models using SkyRL.
It follows the same pattern as mini_swe_agent, but uses the Worker Router architecture
instead of local environment execution.

Usage:
    uv run -m vulrl_inside_skyrl_v2.main_vulrl_skyrl \
        data.train_data="['/path/to/train.parquet']" \
        +generator.http_endpoint_host="localhost" \
        +generator.http_endpoint_port=8001 \
        +generator.rollout_timeout=600 \
        +generator.poll_interval=10

Configuration:
    Worker Router (NOT configurable):
    - Worker Router URL is HARDCODED to http://localhost:12345
    - If running on a different host, use SSH port forwarding:
      ssh -L 12345:remote-host:12345 remote-host
    
    VulRL-specific configs (use + prefix as they're not in standard GeneratorConfig):
    - rollout_timeout: Max time per rollout in seconds (default: 600.0)
    - poll_interval: Status check interval in seconds (default: 10.0)
    - polling_verbose: Enable verbose polling logs (default: True)
    
    Standard SkyRL configs (no + prefix needed):
    - http_endpoint_host: LLM server host (extracted from InferenceEngineClient)
    - http_endpoint_port: LLM server port (extracted from InferenceEngineClient)
"""

import hydra
from omegaconf import DictConfig, OmegaConf
from skyrl_train.entrypoints.main_base import BasePPOExp, config_dir, validate_cfg
from skyrl_train.utils import initialize_ray
import ray

from .ez_vulrl_generator import EzVulRLGenerator


class VulrlPPOExp(BasePPOExp):
    """
    VulRL PPO Experiment class.
    
    Inherits from BasePPOExp and overrides get_generator() to use EzVulRLGenerator
    instead of the default SkyRLGymGenerator.
    """
    
    def get_generator(self, cfg, tokenizer, inference_engine_client):
        """
        Create and return the VulRL generator.
        
        This generator delegates rollout execution to Worker Router via HTTP,
        instead of running environments locally.
        
        Args:
            cfg: Hydra configuration object
            tokenizer: Tokenizer for the model
            inference_engine_client: InferenceEngineClient for extracting LLM endpoint info
            
        Returns:
            EzVulRLGenerator instance
        """
        generator = EzVulRLGenerator(
            generator_cfg=cfg.generator,
            skyrl_gym_cfg=OmegaConf.create({"max_env_workers": 0}),
            inference_engine_client=inference_engine_client,
            tokenizer=tokenizer,
            model_name=self.cfg.trainer.policy.model.path,
        )
        
        return generator


@ray.remote(num_cpus=1)
def skyrl_entrypoint(cfg: DictConfig):
    """
    Ray remote function to run the training loop.
    
    This ensures that the training loop is not run on the head node.
    """
    exp = VulrlPPOExp(cfg)
    exp.run()


@hydra.main(config_path=config_dir, config_name="ppo_base_config", version_base=None)
def main(cfg: DictConfig) -> None:
    """
    Main entry point for VulRL training.
    
    This function:
    1. Validates the configuration
    2. Initializes Ray
    3. Launches the training loop as a Ray remote task
    """
    # Validate the arguments
    validate_cfg(cfg)
    
    # Initialize Ray
    initialize_ray(cfg)
    
    # Run training loop
    ray.get(skyrl_entrypoint.remote(cfg))


if __name__ == "__main__":
    main()
