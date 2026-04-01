"""
LLM Adapter: Makes InferenceEngineClientWrapper compatible with CTFMix Agent.

CTFMix Agent expects a model with:
- model.query(history) -> str
- model.stats (APIStats object)
- model.args (ModelArguments object)
- model.model_metadata (dict with cost info)

This adapter wraps InferenceEngineClientWrapper to provide that interface.
"""

import asyncio
from typing import List, Dict, Any
from .ctfmix.models import APIStats, ModelArguments


class LLMAdapter:
    """
    Adapter that makes InferenceEngineClientWrapper look like a CTFMix model.
    
    CTFMix Agent calls:
        response = self.model.query(history)  # history is list of dicts
    
    We need to convert that to:
        engine_output = await llm_client.generate(engine_input)
    """
    
    def __init__(
        self,
        llm_client,
        model_name: str,
        temperature: float = 0.7,
        max_tokens: int = 512,
        step_limit: int = 30
    ):
        """
        Initialize adapter.
        
        Args:
            llm_client: InferenceEngineClientWrapper instance
            model_name: Model name string
            temperature: Sampling temperature
            max_tokens: Max tokens per generation
            step_limit: Max steps per instance
        """
        self.llm_client = llm_client
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        # Create ModelArguments (CTFMix expects this)
        self.args = ModelArguments(
            model_name=model_name,
            temperature=temperature,
            per_instance_step_limit=step_limit,
            per_instance_cost_limit=0.0,  # No limit
            total_cost_limit=0.0  # No limit
        )
        
        # Initialize stats (CTFMix expects this)
        self.stats = APIStats()
        
        # Model metadata (for cost tracking - set to 0 since we don't track costs)
        self.model_metadata = {
            "max_context": 200000,  # Assume large context
            "cost_per_input_token": 0.0,
            "cost_per_output_token": 0.0,
            "max_tokens": max_tokens
        }
    
    def history_to_messages(
        self,
        history: List[Dict[str, str]],
        is_demonstration: bool = False
    ) -> List[Dict[str, str]]:
        """
        Convert CTFMix history to messages format.
        
        CTFMix history entries have: role, content, (optional: agent, thought, action)
        We need: role, content
        
        Args:
            history: CTFMix history list
            is_demonstration: Whether this is a demonstration
            
        Returns:
            Filtered message list
        """
        if is_demonstration:
            # For demonstrations, skip system messages and return as string
            history = [entry for entry in history if entry["role"] != "system"]
            return "\n".join([entry["content"] for entry in history])
        
        # Return messages with just role and content
        return [{k: v for k, v in entry.items() if k in ["role", "content"]} for entry in history]
    
    def query(self, history: List[Dict[str, str]]) -> str:
        """
        Query the LLM with the given history.
        
        This is the main method CTFMix Agent calls.
        CTFMix calls this from a worker thread, so we need to handle event loop creation.
        
        Args:
            history: List of message dicts with role/content
            
        Returns:
            LLM response string
        """
        # Convert history to messages
        messages = self.history_to_messages(history)
        
        # Build engine input (InferenceEngineClientWrapper format)
        engine_input = {
            "prompts": [messages],
            "sampling_params": {
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
            }
        }
        
        # Call LLM (need to run async in sync context)
        try:
            # CTFMix runs queries in a worker thread, so we need to create a new event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    raise RuntimeError("Event loop is closed")
            except RuntimeError:
                # No event loop in this thread, create a new one
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Run the async generate
            engine_output = loop.run_until_complete(self.llm_client.generate(engine_input))
            
            response = engine_output["responses"][0]
            
            # Update stats (approximate - we don't have actual token counts)
            # Estimate: ~4 chars per token
            estimated_input_tokens = sum(len(m.get("content", "")) for m in messages) // 4
            estimated_output_tokens = len(response) // 4
            self.stats.tokens_sent += estimated_input_tokens
            self.stats.tokens_received += estimated_output_tokens
            self.stats.api_calls += 1
            
            return response
            
        except Exception as e:
            raise RuntimeError(f"LLM query failed: {e}")
    
    def reset_stats(self, other: APIStats = None):
        """Reset model statistics"""
        if other is None:
            self.stats = APIStats(total_cost=self.stats.total_cost)
        else:
            self.stats = other
