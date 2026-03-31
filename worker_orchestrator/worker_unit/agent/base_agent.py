"""
Base agent interface for VulRL worker_unit.

All agents must implement this interface to be compatible with the worker system.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from worker_router.models import TrajectoryStep


class BaseAgent(ABC):
    """
    Abstract base class for all agents.
    
    Agents handle the reasoning and action selection loop for security testing tasks.
    The environment (VulhubAdapter) manages Docker containers and execution.
    
    Design principle:
    - Environment manages infrastructure (Docker, networks, containers)
    - Agent manages reasoning (LLM, parsing, strategy)
    - Clean separation allows swapping agents without changing environment
    """
    
    def __init__(self, env, llm_client, config: Optional[Dict[str, Any]] = None):
        """
        Initialize agent.
        
        Args:
            env: Environment adapter (e.g., VulhubAdapter wrapped in adapter)
            llm_client: LLM client for querying models
            config: Agent-specific configuration
        """
        self.env = env
        self.llm_client = llm_client
        self.config = config or {}
    
    @abstractmethod
    async def run(
        self,
        initial_prompt: str,
        max_steps: int,
        temperature: float = 0.7,
        max_tokens: int = 512
    ) -> List[TrajectoryStep]:
        """
        Run the agent's main loop.
        
        This method orchestrates the agent-environment interaction:
        1. Initialize conversation with initial_prompt
        2. For each step:
            a. Query LLM for next action
            b. Execute action in environment
            c. Observe result
            d. Update conversation history
        3. Return complete trajectory
        
        Args:
            initial_prompt: Initial task description/prompt
            max_steps: Maximum number of interaction steps
            temperature: LLM sampling temperature
            max_tokens: Maximum tokens per LLM generation
            
        Returns:
            List of TrajectoryStep objects representing the complete episode
        """
        pass
    
    @abstractmethod
    def parse_action(self, llm_output: str) -> str:
        """
        Parse LLM output into executable action.
        
        Different agents may have different output formats:
        - DemoAgent: Expects raw bash commands
        - CTFAgent: Expects thought + action in specific format
        
        Args:
            llm_output: Raw output from LLM
            
        Returns:
            Parsed action string ready for environment execution
        """
        pass
    
    def get_name(self) -> str:
        """Return agent name for logging"""
        return self.__class__.__name__
