"""
CTFAgent: Advanced agent based on EnIGMA/CTFMix architecture.

This agent wraps the CTFMix Agent class and adapts it to work with VulRL's
worker_unit infrastructure.
"""

from typing import List, Dict, Any, Optional
from pathlib import Path
from worker_router.models import TrajectoryStep as WorkerTrajectoryStep

from ..base_agent import BaseAgent
from .ctfmix.agents import Agent, AgentArguments
from .ctfmix.models import ModelArguments
from .llm_adapter import LLMAdapter
from .runtime_adapter import VulhubRuntimeAdapter
from .type_converters import ctfmix_trajectory_to_worker


class CTFAgent(BaseAgent):
    """
    Advanced CTF-style agent with sophisticated parsing and features.
    
    Features from CTFMix/EnIGMA:
    - Thought/action parsing (model explains reasoning before acting)
    - Interactive sessions (vim, radare2, python REPL)
    - History summarization (for long episodes)
    - Multi-line commands with heredoc
    - Command blocklists (prevent dangerous commands)
    - Format error recovery (retry if LLM output is malformed)
    - Extensive logging and hooks
    
    This wraps the CTFMix Agent class and adapts it to worker_unit's interface.
    """
    
    def __init__(
        self,
        env,
        llm_client,
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Initialize CTF agent.
        
        Args:
            env: VulhubAdapter instance (must be already setup)
            llm_client: InferenceEngineClientWrapper instance
            config: Agent configuration:
                - config_file: Path to agent config YAML (optional)
                - model_name: Model name for LLM
                - temperature: Sampling temperature
                - max_tokens: Max tokens per generation
                - step_limit: Max steps (overrides env max_steps)
        """
        super().__init__(env, llm_client, config)
        
        # Extract config parameters
        self.model_name = config.get("model_name", "gpt-4")
        self.temperature = config.get("temperature", 0.7)
        self.max_tokens = config.get("max_tokens", 512)
        self.step_limit = config.get("step_limit", 30)
        
        # Path to agent config YAML
        config_file = config.get("config_file")
        if config_file is None:
            # Use default CTF config
            config_file = Path(__file__).parent.parent / "config" / "default_ctf.yaml"
        else:
            config_file = Path(config_file)
        
        if not config_file.exists():
            raise FileNotFoundError(f"Agent config not found: {config_file}")
        
        # Create LLM adapter
        self.llm_adapter = LLMAdapter(
            llm_client=llm_client,
            model_name=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        
        # Create runtime adapter
        self.runtime_adapter = VulhubRuntimeAdapter(
            vulhub_adapter=env,
            task_config={
                "task_id": env.config.get("task_id", "unknown"),
                "max_steps": self.step_limit,
                "service_url": env.service_url,
            }
        )
        
        # Create CTFMix Agent
        agent_args = AgentArguments(
            model=ModelArguments(
                model_name=self.model_name,
                temperature=self.temperature,
                per_instance_step_limit=self.step_limit,
            ),
            config_file=config_file
        )
        
        self.ctfmix_agent = Agent("primary", agent_args)
        
        # Replace CTFMix agent's model with our adapter
        self.ctfmix_agent.model = self.llm_adapter
    
    async def run(
        self,
        initial_prompt: str,
        max_steps: int,
        temperature: float = 0.7,
        max_tokens: int = 512
    ) -> List[WorkerTrajectoryStep]:
        """
        Run CTF agent loop.
        
        This delegates to CTFMix Agent.run() and converts the result.
        
        Args:
            initial_prompt: Initial task description
            max_steps: Maximum steps
            temperature: LLM temperature (overrides __init__)
            max_tokens: Max tokens (overrides __init__)
            
        Returns:
            List of worker_router TrajectoryStep objects
        """
        print(f"[CTFAgent] Starting CTFMix agent run")
        print(f"[CTFAgent] Model: {self.model_name}, Max steps: {max_steps}")
        
        # Update step limit if provided
        if max_steps != self.step_limit:
            self.step_limit = max_steps
            self.ctfmix_agent.model.args.per_instance_step_limit = max_steps
        
        # Prepare setup args for CTFMix Agent
        # Include CTF-specific template variables with defaults for Vulhub tasks
        task_config = self.runtime_adapter.task_config
        setup_args = {
            "task_id": self.runtime_adapter.task_id,
            "service_url": self.runtime_adapter.service_url,
            "issue": initial_prompt,  # CTFMix calls it "issue"
            # CTF template variables (used in default_ctf.yaml) - use defaults if not provided
            "flag_format": task_config.get("flag_format") or "FLAG{...}",
            "category_friendly": task_config.get("category_friendly") or "security",
            "name": task_config.get("name") or self.runtime_adapter.task_id,
            "points": task_config.get("points") or 100,
            "description": task_config.get("description") or initial_prompt,
            "files": task_config.get("files") or "N/A",
            "server_description": task_config.get("server_description") or f"The target server is accessible at {self.runtime_adapter.service_url}",
        }
        
        try:
            # Run CTFMix Agent (this is a sync call)
            # CTFMix Agent.run() returns (info, trajectory)
            info, ctf_trajectory = self.ctfmix_agent.run(
                setup_args=setup_args,
                env=self.runtime_adapter,
                observation=None,  # Will call reset() internally
                traj_dir=None,  # Use relative path (CTFMix prepends workspace root)
                return_type="info_trajectory",
                init_model_stats=None
            )
            
            print(f"[CTFAgent] CTFMix agent completed")
            print(f"[CTFAgent] Steps: {len(ctf_trajectory)}")
            print(f"[CTFAgent] Exit status: {info.get('exit_status', 'unknown')}")
            print(f"[CTFAgent] Submission: {info.get('submission', 'none')}")
            
            # Convert CTFMix trajectory to worker_router format
            worker_trajectory = ctfmix_trajectory_to_worker(ctf_trajectory, info)
            
            return worker_trajectory
            
        except Exception as e:
            print(f"[CTFAgent] Error running CTFMix agent: {e}")
            import traceback
            traceback.print_exc()
            
            # Return minimal error trajectory
            return [WorkerTrajectoryStep(
                step=0,
                action="error",
                observation=f"Agent error: {str(e)}",
                reward=0.0,
                done=True,
                metadata={"error": str(e), "error_type": type(e).__name__}
            )]
    
    def parse_action(self, llm_output: str) -> str:
        """
        Parse LLM output into action.
        
        CTFMix handles this internally, so this is just for interface compliance.
        
        Args:
            llm_output: Raw LLM output
            
        Returns:
            Parsed action
        """
        # CTFMix uses ThoughtActionParser which extracts code from ``` blocks
        # This is handled internally by the Agent, so we don't need to implement it here
        return llm_output
