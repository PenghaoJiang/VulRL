"""
Type converters between CTFMix types and worker_router types.

CTFMix uses its own TrajectoryStep format (with thought, response, state).
worker_router uses a different TrajectoryStep format (with step, action, observation, reward).

This module handles bidirectional conversion.
"""

from typing import List, Dict, Any
from worker_router.models import TrajectoryStep as WorkerTrajectoryStep
from .ctfmix.types import TrajectoryStep as CTFTrajectoryStep, AgentInfo


def ctfmix_trajectory_to_worker(
    ctf_trajectory: List[CTFTrajectoryStep],
    agent_info: AgentInfo
) -> List[WorkerTrajectoryStep]:
    """
    Convert CTFMix trajectory to worker_router trajectory format.
    
    CTFMix TrajectoryStep:
        - action: str (the command executed)
        - observation: str (output from execution)
        - response: str (raw LLM output before parsing)
        - state: str (environment state JSON)
        - thought: str (LLM reasoning)
        - execution_time: float
    
    Worker TrajectoryStep:
        - step: int
        - action: str
        - observation: str
        - reward: float
        - done: bool
        - metadata: Dict[str, Any]
    
    Args:
        ctf_trajectory: CTFMix trajectory
        agent_info: CTFMix agent info (contains exit_status, submission, etc.)
        
    Returns:
        List of worker_router TrajectoryStep objects
    """
    worker_trajectory = []
    
    for idx, ctf_step in enumerate(ctf_trajectory):
        # Determine if this is the last step
        is_last_step = (idx == len(ctf_trajectory) - 1)
        
        # Extract done status from agent_info if last step
        if is_last_step:
            exit_status = agent_info.get("exit_status", "unknown")
            done = exit_status in ["submitted", "step_limit", "task_timeout", "exit_format", "exit_error", "exit_context", "exit_cost"]
        else:
            done = False
        
        # Build metadata from CTF step
        metadata = {
            "thought": ctf_step.get("thought", ""),
            "response": ctf_step.get("response", ""),
            "state": ctf_step.get("state", ""),
            "execution_time": ctf_step.get("execution_time", 0.0),
        }
        
        # Add agent_info to last step's metadata
        if is_last_step:
            metadata["agent_info"] = dict(agent_info)
        
        worker_step = WorkerTrajectoryStep(
            step=idx,
            action=ctf_step.get("action", ""),
            observation=ctf_step.get("observation", ""),
            reward=0.0,  # Will be computed by reward calculator
            done=done,
            metadata=metadata
        )
        
        worker_trajectory.append(worker_step)
    
    return worker_trajectory


def worker_action_to_ctfmix(action: str) -> str:
    """
    Convert worker action format to CTFMix format.
    
    Currently a pass-through since both use string actions.
    Future: might need to handle different action formats.
    
    Args:
        action: Action string from worker system
        
    Returns:
        Action string for CTFMix
    """
    return action


def extract_final_reward(agent_info: AgentInfo) -> float:
    """
    Extract final reward from CTFMix agent_info.
    
    CTFMix uses:
    - exit_status: "submitted" (success), "wrong_submission" (failure), etc.
    - score: 1.0 (correct flag), 0.0 (wrong flag)
    
    Args:
        agent_info: CTFMix agent info dictionary
        
    Returns:
        Final reward (1.0 for success, 0.0 for failure/incomplete)
    """
    exit_status = agent_info.get("exit_status", "unknown")
    
    if exit_status == "submitted":
        return agent_info.get("score", 1.0)
    elif exit_status == "wrong_submission":
        return 0.0
    else:
        # Incomplete or error
        return 0.0
