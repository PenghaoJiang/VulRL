"""
DemoAgent: Simple agent that parses bash commands from LLM output.

This is the original simple agent logic extracted from agent_loop.py.
It expects the LLM to generate bash commands directly.
"""

from typing import List, Dict, Any
from worker_router.models import TrajectoryStep
from ..base_agent import BaseAgent


class DemoAgent(BaseAgent):
    """
    Simple demonstration agent.
    
    Behavior:
    - Sends task prompt + observations to LLM
    - Expects LLM to generate bash commands directly
    - No sophisticated parsing (just treats LLM output as raw command)
    - Minimal error handling
    
    This agent uses the original simple logic from agent_loop.py.
    """
    
    def __init__(self, env, llm_client, config: Dict[str, Any] = None):
        super().__init__(env, llm_client, config)
        
    async def run(
        self,
        initial_prompt: str,
        max_steps: int,
        temperature: float = 0.7,
        max_tokens: int = 512
    ) -> List[TrajectoryStep]:
        """
        Run simple agent loop.
        
        This implements the original logic from agent_loop.py:
        1. Initialize conversation with system prompt + task
        2. For each step:
            - Query LLM with current messages
            - Parse action (just use raw output as bash command)
            - Execute in environment
            - Append to conversation
        3. Return trajectory
        """
        # Initialize conversation (same as original agent_loop.py)
        messages = [
            {"role": "system", "content": "You are a penetration testing agent. Provide concrete bash commands."},
            {"role": "user", "content": initial_prompt}
        ]
        
        trajectory = []
        observation = initial_prompt  # First observation is the task description
        
        for step in range(max_steps):
            print(f"[DemoAgent] Step {step + 1}/{max_steps}")
            
            # 1. Query LLM (same as original line 51-66 in agent_loop.py)
            engine_input = {
                "prompts": [messages],
                "sampling_params": {
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                }
            }
            
            try:
                engine_output = await self.llm_client.generate(engine_input)
                action = engine_output["responses"][0]
                print(f"[DemoAgent] Action: {action[:100]}...")
            except Exception as e:
                print(f"[DemoAgent] Error generating action: {e}")
                action = "echo 'Error: LLM generation failed'"
            
            # 2. Execute in environment (same as original line 68-80)
            try:
                observation_str, reward, terminated, truncated, info = self.env.step(action)
                done = terminated or truncated
                
                # Convert observation to string if needed
                if hasattr(observation_str, 'to_text'):
                    observation = observation_str.to_text()
                elif hasattr(observation_str, 'text'):
                    observation = observation_str.text
                else:
                    observation = str(observation_str)
                
                print(f"[DemoAgent] Observation: {observation[:100]}...")
                print(f"[DemoAgent] Reward: {reward}, Done: {done}")
            except Exception as e:
                print(f"[DemoAgent] Error executing step: {e}")
                observation = f"Error: {str(e)}"
                reward = 0.0
                done = True
                info = {}
            
            # 3. Store trajectory step (same as original line 82-90)
            trajectory.append(TrajectoryStep(
                step=step,
                action=action,
                observation=observation,
                reward=reward,
                done=done,
                metadata=info
            ))
            
            # 4. Update conversation (same as original line 92-95)
            messages.append({"role": "assistant", "content": action})
            if not done:
                messages.append({"role": "user", "content": observation})
            
            # 5. Check if done (same as original line 97-100)
            if done:
                print(f"[DemoAgent] Episode finished at step {step + 1}")
                break
        
        return trajectory
    
    def parse_action(self, llm_output: str) -> str:
        """
        DemoAgent doesn't parse - just uses raw LLM output as bash command.
        
        Args:
            llm_output: Raw LLM output
            
        Returns:
            Same as input (no parsing)
        """
        return llm_output.strip()
