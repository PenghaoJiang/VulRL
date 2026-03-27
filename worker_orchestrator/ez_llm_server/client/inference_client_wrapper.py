"""
InferenceEngineClientWrapper - Mimics SkyRL's InferenceEngineClient interface.

This wrapper provides the same API as SkyRL's InferenceEngineClient but uses
HTTP requests to a vLLM server under the hood.
"""

import aiohttp
from typing import List, Dict, Any, Optional, TypedDict


class InferenceEngineInput(TypedDict, total=False):
    """Input format matching SkyRL's InferenceEngineInput."""
    prompts: Optional[List[List[Dict[str, str]]]]  # List of conversation histories
    prompt_token_ids: Optional[List[List[int]]]    # Or token IDs directly
    sampling_params: Optional[Dict[str, Any]]       # Sampling parameters


class InferenceEngineOutput(TypedDict):
    """Output format matching SkyRL's InferenceEngineOutput."""
    responses: List[str]          # Generated text responses
    stop_reasons: List[str]       # Stop reasons (e.g., "stop", "length")
    response_ids: List[List[int]] # Token IDs of responses


class InferenceEngineClientWrapper:
    """Mimics SkyRL's InferenceEngineClient interface.
    
    This provides the same API as SkyRL's InferenceEngineClient but uses
    HTTP requests to communicate with a vLLM server.
    
    Usage:
        client = InferenceEngineClientWrapper(
            endpoint="http://127.0.0.1:8001",
            model_name="Qwen/Qwen2.5-7B-Instruct"
        )
        
        engine_input = {
            "prompts": [[
                {"role": "user", "content": "Hello!"}
            ]],
            "sampling_params": {"max_tokens": 50, "temperature": 0.7}
        }
        
        output = await client.generate(engine_input)
        response = output["responses"][0]
    """
    
    def __init__(
        self,
        endpoint: str = "http://127.0.0.1:8001",
        model_name: str = "Qwen/Qwen2.5-7B-Instruct",
    ):
        """Initialize client.
        
        Args:
            endpoint: vLLM server endpoint
            model_name: Model name (must match server)
        """
        self.endpoint = endpoint.rstrip("/")
        self.model_name = model_name
    
    async def generate(self, input_batch: InferenceEngineInput) -> InferenceEngineOutput:
        """Generate responses for input batch.
        
        This method mimics SkyRL's InferenceEngineClient.generate() interface.
        
        Args:
            input_batch: Input containing either prompts or prompt_token_ids,
                        and optional sampling_params
        
        Returns:
            Dictionary with:
                - responses: List of generated text
                - stop_reasons: List of stop reasons
                - response_ids: List of token ID lists (empty for now)
        
        Example:
            input_batch = {
                "prompts": [[
                    {"role": "system", "content": "You are helpful."},
                    {"role": "user", "content": "Write hello world in Python"}
                ]],
                "sampling_params": {
                    "max_tokens": 100,
                    "temperature": 0.7,
                }
            }
            output = await client.generate(input_batch)
            print(output["responses"][0])
        """
        prompts = input_batch.get("prompts")
        sampling_params = input_batch.get("sampling_params", {})
        
        if prompts is None:
            raise ValueError("prompts must be provided in input_batch")
        
        # Extract sampling parameters
        max_tokens = sampling_params.get("max_tokens", 512)
        temperature = sampling_params.get("temperature", 0.7)
        top_p = sampling_params.get("top_p", 1.0)
        stop = sampling_params.get("stop", None)
        
        # Process each prompt in batch
        responses = []
        stop_reasons = []
        
        for messages in prompts:
            # Call vLLM HTTP endpoint
            response_text, stop_reason = await self._query_vllm(
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stop=stop,
            )
            responses.append(response_text)
            stop_reasons.append(stop_reason)
        
        return {
            "responses": responses,
            "stop_reasons": stop_reasons,
            "response_ids": [[] for _ in responses],  # Empty for now
        }
    
    async def _query_vllm(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 1.0,
        stop: Optional[List[str]] = None,
    ) -> tuple[str, str]:
        """Query vLLM server via HTTP.
        
        Args:
            messages: Conversation history
            max_tokens: Max tokens to generate
            temperature: Sampling temperature
            top_p: Nucleus sampling parameter
            stop: Stop sequences
        
        Returns:
            Tuple of (response_text, stop_reason)
        """
        url = f"{self.endpoint}/v1/chat/completions"
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "top_p": top_p,
        }
        
        if stop is not None:
            payload["stop"] = stop
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise RuntimeError(
                        f"vLLM server returned status {resp.status}: {error_text}"
                    )
                
                result = await resp.json()
                
                # Extract response
                choice = result["choices"][0]
                response_text = choice["message"]["content"]
                stop_reason = choice["finish_reason"]
                
                return response_text, stop_reason
