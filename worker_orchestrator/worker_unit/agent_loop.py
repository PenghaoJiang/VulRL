"""
Simplified agent loop from SkyRL skyrl_gym_generator.py.
Adapted for worker_unit - no tokenization, just string-based interaction.
"""

from typing import List
from worker_router.models import TrajectoryStep


async def agent_loop(
    env,
    llm_client,
    initial_prompt: str,
    observation: str,
    max_steps: int,
    temperature: float,
    max_tokens: int
) -> List[TrajectoryStep]:
    """
    Run the agent-environment interaction loop.
    
    Simplified from SkyRL's skyrl_gym_generator.py (lines 300-400):
    - Keep: LLM generate, env.step, loop control
    - Remove: tokenization, loss masks, logprobs
    
    Args:
        env: SecurityEnv instance
        llm_client: InferenceEngineClientWrapper (mimics SkyRL's client)
        initial_prompt: Initial task prompt
        observation: Initial observation from env.reset()
        max_steps: Maximum steps
        temperature: LLM temperature
        max_tokens: Max tokens per LLM call
        
    Returns:
        List of TrajectoryStep
    """
    
    # Initialize conversation
    messages = [
        {"role": "system", "content": "You are a penetration testing agent. Provide concrete bash commands."},
        {"role": "user", "content": initial_prompt},
        {"role": "user", "content": observation}
    ]
    
    trajectory = []
    
    for step in range(max_steps):
        print(f"[AgentLoop] Step {step + 1}/{max_steps}")
        
        # 1. LLM generate (same as SkyRL line 306)
        engine_input = {
            "prompts": [messages],
            "sampling_params": {
                "max_tokens": max_tokens,
                "temperature": temperature,
            }
        }
        
        try:
            engine_output = await llm_client.generate(engine_input)
            action = engine_output["responses"][0]
            print(f"[AgentLoop] Action: {action[:100]}...")
        except Exception as e:
            print(f"[AgentLoop] Error generating action: {e}")
            action = "echo 'Error: LLM generation failed'"
        
        # 2. Environment step (same as SkyRL line 333)
        # env.step returns: (observation, reward, terminated, truncated, info)
        try:
            observation, reward, terminated, truncated, info = env.step(action)
            done = terminated or truncated
            print(f"[AgentLoop] Observation: {observation[:100]}...")
            print(f"[AgentLoop] Reward: {reward}, Done: {done}")
        except Exception as e:
            print(f"[AgentLoop] Error executing step: {e}")
            observation = f"Error: {str(e)}"
            reward = 0.0
            done = True
            info = {}
        
        # 3. Store trajectory step
        trajectory.append(TrajectoryStep(
            step=step,
            action=action,
            observation=observation,
            reward=reward,  # TODO: Currently 0.0
            done=done,
            metadata=info
        ))
        
        # 4. Update conversation
        messages.append({"role": "assistant", "content": action})
        if not done:
            messages.append({"role": "user", "content": observation})
        
        # 5. Check done
        if done:
            print(f"[AgentLoop] Episode finished at step {step + 1}")
            break
    
    return trajectory
