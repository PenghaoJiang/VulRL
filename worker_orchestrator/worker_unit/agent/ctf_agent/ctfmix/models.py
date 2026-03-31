# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.  

# SPDX-License-Identifier: CC-BY-NC-4.0


#
from __future__ import annotations

import copy
import json
import logging
import yaml
from collections import defaultdict
from dataclasses import dataclass, fields
from pathlib import Path

# Core dependencies (always required)
from openai import AzureOpenAI, BadRequestError, OpenAI
from simple_parsing.helpers.serialization.serializable import FrozenSerializable, Serializable
from tenacity import (
    retry,
    retry_if_not_exception_type,
    stop_after_attempt,
    wait_random_exponential,
)

# Optional provider imports (commented out - not needed for VulRL)
# from anthropic import AI_PROMPT, HUMAN_PROMPT, Anthropic, AnthropicBedrock
# from groq import Groq
# import together
# import boto3
# from botocore.config import Config

from .commands import Command
from .config import find_ctfmix_models_config_path, keys_config
from .log import get_logger
import requests
import re

logger = get_logger("api_models")

_MAX_RETRIES = int(keys_config.get("SWE_AGENT_MODEL_MAX_RETRIES", 10))


def _as_float(value, default: float = 0.0) -> float:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    return float(str(value))


def _as_int(value, default: int = 0) -> int:
    if value is None:
        return default
    if isinstance(value, int):
        return value
    return int(float(str(value)))

# Load model configurations from YAML
def load_model_configs():
    """Load model configurations from YAML file"""
    config_path = find_ctfmix_models_config_path()
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    return config

def get_model_metadata(model_name: str, provider_configs: dict, shortcuts: dict, defaults: dict) -> dict:
    """Get model metadata with default values for missing fields"""
    # Check shortcuts first
    actual_model = shortcuts.get(model_name, model_name)
    
    # Get model config
    model_config = provider_configs.get(actual_model, {})
    
    # Apply defaults for missing values
    metadata = {
        'max_context': _as_int(model_config.get('max_context', defaults['max_context'])),
        'cost_per_input_token': _as_float(model_config.get('cost_per_input_token', defaults['cost_per_input_token'])),
        'cost_per_output_token': _as_float(model_config.get('cost_per_output_token', defaults['cost_per_output_token'])),
    }
    
    # Add optional fields if present
    if 'max_tokens' in model_config:
        metadata['max_tokens'] = _as_int(model_config['max_tokens'])
    elif 'max_tokens' in defaults:
        metadata['max_tokens'] = _as_int(defaults['max_tokens'])
    
    return metadata

def clean_result(result):
    # First, split on </think> and take everything after the first one (if any)
    if "</think>" in result:
        content = " ".join(result.split("</think>")[1:])
    else:
        content = result
    content = content.split("<|im_end|>")[0]
    
    # print(f"Content: {result}")
    # exit()
    # # Now, remove all <|...|> patterns including Unicode variants
    import re
    # # Remove all <|...|> patterns - this pattern matches < followed by any pipe-like character, then any content, then pipe-like character and >
    
    # Also remove specific tool call patterns
    tool_patterns = [
        r"<｜tool▁call▁begin｜>.*?<｜tool▁call▁end｜>",
        r"<｜tool▁calls▁begin｜>.*?<｜tool▁calls▁end｜>",
    ]
    # Use a loop to handle nested patterns
    for pattern in tool_patterns:
        while re.search(pattern, content, flags=re.DOTALL):
            content = re.sub(pattern, "", content, flags=re.DOTALL)

    content = content.replace("<｜tool▁call▁begin｜>", "").replace("<｜tool▁call▁end｜>", "").replace("<｜tool▁calls▁begin｜>", "").replace("<｜tool▁calls▁end｜>", "")
    
    return content.strip()

@dataclass(frozen=True)
class ModelArguments(FrozenSerializable):
    """Arguments configuring the model and its behavior."""

    # Name of the model to use
    model_name: str
    # Cost limit for every instance (task)
    per_instance_cost_limit: float = 0.0
    # Total cost limit
    total_cost_limit: float = 0.0
    # Sampling temperature
    temperature: float = 0.0
    # Sampling top-p
    top_p: float = 1.0
    # Sampling top-k
    top_k: int = 20
    # Path to replay file when using the replay model
    replay_path: str | None = None
    # Host URL when using Ollama model
    host_url: str = "localhost:11434"
    # Maximum number of steps (environment interactions) per instance (0 = unlimited)
    per_instance_step_limit: int = 0


@dataclass
class APIStats(Serializable):
    total_cost: float = 0
    instance_cost: float = 0
    tokens_sent: int = 0
    tokens_received: int = 0
    api_calls: int = 0

    def __add__(self, other):
        if not isinstance(other, APIStats):
            msg = "Can only add APIStats with APIStats"
            raise TypeError(msg)

        return APIStats(
            **{field.name: getattr(self, field.name) + getattr(other, field.name) for field in fields(self)},
        )

    def replace(self, other):
        if not isinstance(other, APIStats):
            msg = "Can only replace APIStats with APIStats"
            raise TypeError(msg)

        return APIStats(**{field.name: getattr(other, field.name) for field in fields(self)})


class ContextWindowExceededError(Exception):
    pass


class CostLimitExceededError(Exception):
    pass


class BaseModel:
    def __init__(self, args: ModelArguments, commands: list[Command]):
        self.args = args
        self.commands = commands
        self.model_metadata = {}
        self.stats = APIStats()

        # Load configurations from YAML
        configs = load_model_configs()
        defaults = configs['defaults']
        
        # Get provider-specific configs and shortcuts
        provider_configs, shortcuts = self._get_provider_configs(configs)
        
        # Map `model_name` to API-compatible name `api_model`
        self.api_model = shortcuts.get(self.args.model_name, self.args.model_name)

        # Handle special model name prefixes
        if args.model_name.startswith("ft:"):
            ft_model = args.model_name.split(":")[1]
            self.model_metadata = get_model_metadata(ft_model, provider_configs, shortcuts, defaults)
        elif args.model_name.startswith("ollama:"):
            self.api_model = args.model_name.split("ollama:", 1)[1]
            # Ollama models use default metadata
            self.model_metadata = get_model_metadata(self.api_model, {}, {}, defaults)
        elif args.model_name.startswith("azure:"):
            azure_model = args.model_name.split("azure:", 1)[1]
            self.model_metadata = get_model_metadata(azure_model, provider_configs, shortcuts, defaults)
        elif args.model_name.startswith("bedrock:"):
            self.api_model = args.model_name.split("bedrock:", 1)[1]
            bedrock_configs = configs.get('bedrock_models', {})
            self.model_metadata = get_model_metadata(self.api_model, bedrock_configs, {}, defaults)
        elif args.model_name.startswith("groq:"):
            self.api_model = args.model_name.split("groq:", 1)[1]
            groq_configs = configs.get('groq_models', {})
            groq_shortcuts = configs.get('groq_shortcuts', {})
            self.model_metadata = get_model_metadata(self.api_model, groq_configs, groq_shortcuts, defaults)
        elif args.model_name.startswith("vllm:"):
            # VLLM models use default metadata
            self.model_metadata = get_model_metadata(self.args.model_name, {}, {}, defaults)
        else:
            # Try to find model in any provider configs
            self.model_metadata = get_model_metadata(args.model_name, provider_configs, shortcuts, defaults)
            
            # If model not found anywhere, check special models
            if not any(key in self.model_metadata for key in ['max_context']) or self.model_metadata.get('max_context') == defaults['max_context']:
                special_configs = configs.get('special_models', {})
                if args.model_name in special_configs:
                    self.model_metadata = get_model_metadata(args.model_name, special_configs, {}, defaults)
                elif self.api_model not in provider_configs and args.model_name not in shortcuts:
                    msg = f"Unregistered model ({args.model_name}). Add model to models_config.yaml"
                    logger.warning(msg)
                    # Use defaults for unknown models
                    self.model_metadata = defaults.copy()

    def _get_provider_configs(self, configs: dict) -> tuple[dict, dict]:
        """Get the appropriate provider configs and shortcuts based on model class"""
        # This method should be overridden by subclasses to return the right configs
        return {}, {}

    def reset_stats(self, other: APIStats | None = None):
        if other is None:
            self.stats = APIStats(total_cost=self.stats.total_cost)
            logger.info("Resetting model stats")
        else:
            # Make sure to copy the stats to avoid modifying the original
            self.stats = copy.deepcopy(other)

    def update_stats(self, input_tokens: int, output_tokens: int) -> float:
        """
        Calculates the cost of a response from the openai API.

        Args:
        input_tokens (int): The number of tokens in the prompt.
        output_tokens (int): The number of tokens in the response.

        Returns:
        float: The cost of the response.
        """
        # Calculate cost and update cost related fields
        cost = (
            self.model_metadata.get("cost_per_input_token", 0.0) * input_tokens
            + self.model_metadata.get("cost_per_output_token", 0.0) * output_tokens
        )
        self.stats.total_cost += cost
        self.stats.instance_cost += cost
        self.stats.tokens_sent += input_tokens
        self.stats.tokens_received += output_tokens
        self.stats.api_calls += 1

        # Log updated cost values to std. err
        logger.debug(
            f"input_tokens={input_tokens:,}, "
            f"output_tokens={output_tokens:,}, "
            f"instance_cost={self.stats.instance_cost:.2f}, "
            f"cost={cost:.2f}",
        )
        logger.debug(
            f"total_tokens_sent={self.stats.tokens_sent:,}, "
            f"total_tokens_received={self.stats.tokens_received:,}, "
            f"total_cost={self.stats.total_cost:.2f}, "
            f"total_api_calls={self.stats.api_calls:,}",
        )

        # Check whether total cost or instance cost limits have been exceeded
        if 0 < self.args.total_cost_limit <= self.stats.total_cost:
            logger.warning(f"Cost {self.stats.total_cost:.2f} exceeds limit {self.args.total_cost_limit:.2f}")
            msg = "Total cost limit exceeded"
            raise CostLimitExceededError(msg)

        if 0 < self.args.per_instance_cost_limit <= self.stats.instance_cost:
            logger.warning(f"Cost {self.stats.instance_cost:.2f} exceeds limit {self.args.per_instance_cost_limit:.2f}")
            msg = "Instance cost limit exceeded"
            raise CostLimitExceededError(msg)
        return cost

    def query(self, history: list[dict[str, str]]) -> str:
        msg = "Use a subclass of BaseModel"
        raise NotImplementedError(msg)


class OpenAIModel(BaseModel):
    def _get_provider_configs(self, configs: dict) -> tuple[dict, dict]:
        return configs.get('openai_models', {}), configs.get('openai_shortcuts', {})

    def __init__(self, args: ModelArguments, commands: list[Command]):
        super().__init__(args, commands)

        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

        self._setup_client()
        # Track all previous responses to detect duplicates
        self.previous_responses = []

    def _setup_client(self):
        if self.args.model_name.startswith("azure"):
            logger.warning(
                "The --model CLI argument is ignored when using the Azure GPT endpoint. "
                "The model is determined by the AZURE_OPENAI_DEPLOYMENT key/"
                "environment variable (this might change in the future).",
            )
            self.api_model = keys_config["AZURE_OPENAI_DEPLOYMENT"]
            self.client = AzureOpenAI(
                api_key=keys_config["AZURE_OPENAI_API_KEY"],
                azure_endpoint=keys_config["AZURE_OPENAI_ENDPOINT"],
                api_version=keys_config.get("AZURE_OPENAI_API_VERSION", "2024-02-01"),
            )
        else:
            api_base_url: str | None = keys_config.get("OPENAI_API_BASE_URL", None)
            self.client = OpenAI(api_key=keys_config["OPENAI_API_KEY"], base_url=api_base_url)

    def history_to_messages(
        self,
        history: list[dict[str, str]],
        is_demonstration: bool = False,
    ) -> str | list[dict[str, str]]:
        """
        Create `messages` by filtering out all keys except for role/content per `history` turn
        """
        # Remove system messages if it is a demonstration
        if is_demonstration:
            history = [entry for entry in history if entry["role"] != "system"]
            return "\n".join([entry["content"] for entry in history])
        # Return history components with just role, content fields
        return [{k: v for k, v in entry.items() if k in ["role", "content"]} for entry in history]

    @retry(
        wait=wait_random_exponential(min=1, max=15),
        reraise=True,
        stop=stop_after_attempt(_MAX_RETRIES),
        retry=retry_if_not_exception_type((CostLimitExceededError, RuntimeError)),
    )
    def query(self, history: list[dict[str, str]]) -> str:
        """
        Query the OpenAI API with the given `history` and return the response.
        """
        max_resample_attempts = 10
        resample_count = 0
        
        while resample_count < max_resample_attempts:
            try:
                # Perform OpenAI API call
                response = self.client.chat.completions.create(
                    messages=self.history_to_messages(history),
                    model=self.api_model,
                    temperature=self.args.temperature,
                    top_p=self.args.top_p,
                )
                break
            except BadRequestError as e:
                logger.exception("BadRequestError")
                if "context window" in str(e) or getattr(e, "error", {}).get("code") == "context_length_exceeded":
                    msg = f"Context window ({self.model_metadata.get('max_context', 'unknown')} tokens) exceeded"
                    raise ContextWindowExceededError(msg) from e
                else:
                    raise e
            
        # Calculate + update costs, get response
        input_tokens = response.usage.prompt_tokens
        output_tokens = response.usage.completion_tokens
        self.update_stats(input_tokens, output_tokens)
        current_response = clean_result(response.choices[0].message.content)
        
        # Store this response for future comparison
        self.previous_responses.append(current_response.strip())
        return current_response


class DeepSeekModel(OpenAIModel):
    def _get_provider_configs(self, configs: dict) -> tuple[dict, dict]:
        return configs.get('deepseek_models', {}), {}

    def _setup_client(self) -> None:
        api_base_url: str = keys_config["DEEPSEEK_API_BASE_URL"]
        self.client = OpenAI(api_key=keys_config["DEEPSEEK_API_KEY"], base_url=api_base_url)


# ============================================================================
# NON-OPENAI PROVIDERS COMMENTED OUT (keeping only OpenAI provider)
# ============================================================================

# class GroqModel(OpenAIModel):
#     def _get_provider_configs(self, configs: dict) -> tuple[dict, dict]:
#         return configs.get('groq_models', {}), configs.get('groq_shortcuts', {})
# 
#     def _setup_client(self) -> None:
#         self.client = Groq(
#             api_key=keys_config["GROQ_API_KEY"],
#         )


# class AnthropicModel(BaseModel):
#     def _get_provider_configs(self, configs: dict) -> tuple[dict, dict]:
#         return configs.get('anthropic_models', {}), configs.get('anthropic_shortcuts', {})
# 
#     def __init__(self, args: ModelArguments, commands: list[Command]):
#         super().__init__(args, commands)
# 
#         # Set Anthropic key
#         self.api = Anthropic(api_key=keys_config["ANTHROPIC_API_KEY"])
# 
#     def history_to_messages(
#         self,
#         history: list[dict[str, str]],
#         is_demonstration: bool = False,
#     ) -> str | list[dict[str, str]]:
#         """
#         Create `prompt` by filtering out all keys except for role/content per `history` turn
#         Reference: https://docs.anthropic.com/claude/reference/complete_post
#         """
#         return anthropic_history_to_messages(self, history, is_demonstration)
# 
#     @retry(
#         wait=wait_random_exponential(min=1, max=15),
#         reraise=True,
#         stop=stop_after_attempt(_MAX_RETRIES),
#         retry=retry_if_not_exception_type((CostLimitExceededError, RuntimeError)),
#     )
#     def query(self, history: list[dict[str, str]]) -> str:
#         """
#         Query the Anthropic API with the given `history` and return the response.
#         """
#         return anthropic_query(self, history)


# class BedrockModel(BaseModel):  # COMMENTED OUT - AWS Bedrock not needed
#     def _get_provider_configs(self, configs: dict) -> tuple[dict, dict]:
#         return {}, {}
#     ...methods omitted...

# Bedrock helper function also commented out
def deepseek_query_DISABLED(model, history: list[dict[str, str]]) -> str:
    """Bedrock query function - DISABLED"""
    pass  # ~70 lines omitted


if False:  # Disabled - Ollama not needed for VulRL
    class OllamaModel(BaseModel):
        def __init__(self, args, commands):
            pass
        def query(self, history):
            pass


if False:  # Disabled - Together not needed for VulRL  
    class TogetherModel(BaseModel):
        def __init__(self, args, commands):
            pass
        def query(self, history):
            pass


class HumanModel(BaseModel):
    def _get_provider_configs(self, configs: dict) -> tuple[dict, dict]:
        return {}, {}

    def __init__(self, args: ModelArguments, commands: list[Command]):
        super().__init__(args, commands)

        # Determine which commands require multi-line input
        self.multi_line_command_endings = {
            command.name: command.end_name for command in commands if command.end_name is not None
        }

    def history_to_messages(
        self,
        history: list[dict[str, str]],
        is_demonstration: bool = False,
    ) -> str | list[dict[str, str]]:
        """
        Create `messages` by filtering out all keys except for role/content per `history` turn
        """
        # Remove system messages if it is a demonstration
        if is_demonstration:
            history = [entry for entry in history if entry["role"] != "system"]
            return "\n".join([entry["content"] for entry in history])
        # Return history components with just role, content fields
        return [{k: v for k, v in entry.items() if k in ["role", "content"]} for entry in history]

    def query(self, history: list[dict[str, str]], action_prompt: str = "> ") -> str:
        """
        Logic for handling user input to pass to SWEEnv
        """
        action = input(action_prompt)
        command_name = action.split()[0] if action.strip() else ""

        # Special handling for multi-line input actions (i.e. edit)
        if command_name in self.multi_line_command_endings:
            buffer = [action]
            end_keyword = self.multi_line_command_endings[command_name]
            while True:
                action = input("... ")
                buffer.append(action)
                if action.rstrip() == end_keyword:
                    # Continue reading input until terminating keyword inputted
                    break
            action = "\n".join(buffer)
        elif action.strip() == "start_multiline_command":  # do arbitrary multi-line input
            buffer = []
            while True:
                action = input("... ")
                if action.rstrip() == "end_multiline_command":
                    break
                buffer.append(action)
            action = "\n".join(buffer)
        return action


class HumanThoughtModel(HumanModel):
    def _get_provider_configs(self, configs: dict) -> tuple[dict, dict]:
        return {}, {}

    def query(self, history: list[dict[str, str]]) -> str:
        """
        Logic for handling user input (both thought + action) to pass to SWEEnv
        """
        thought_all = ""
        thought = input("Thought (end w/ END_THOUGHT): ")
        while True:
            if "END_THOUGHT" in thought:
                thought = thought.split("END_THOUGHT")[0]
                thought_all += thought
                break
            thought_all += thought
            thought = input("... ")

        action = super().query(history, action_prompt="Action: ")

        return f"{thought_all}\n```\n{action}\n```"


class ReplayModel(BaseModel):
    def _get_provider_configs(self, configs: dict) -> tuple[dict, dict]:
        return {}, {}

    def __init__(self, args: ModelArguments, commands: list[Command]):
        super().__init__(args, commands)

        if self.args.replay_path is None or not Path(self.args.replay_path).exists():
            msg = "--replay_path must point to a file that exists to run a replay policy"
            raise ValueError(msg)

        self.replays = [
            list(json.loads(x).values())[0] for x in Path(self.args.replay_path).read_text().splitlines(keepends=True)
        ]
        self.replay_idx = 0
        self.action_idx = 0

    def _next_replay(self) -> None:
        """Called after last action"""
        self.replay_idx += 1
        self.action_idx = 0

    def query(self, history: list[dict[str, str]]) -> str:
        """
        Logic for tracking which replay action to pass to SWEEnv
        """
        actions = self.replays[self.replay_idx]
        try:
            action = actions[self.action_idx]
        except IndexError:
            msg = (
                "This seems to be an incomplete trajectory. "
                "We reached the end of it, but `submit` was not called. "
                "Calling it now."
            )
            logger.warning(msg)
            action = "```\nsubmit\n```"

        self.action_idx += 1

        # Assuming `submit` is always last action of replay trajectory
        if action == "submit":
            self._next_replay()

        return action


class InstantEmptySubmitTestModel(BaseModel):
    def _get_provider_configs(self, configs: dict) -> tuple[dict, dict]:
        return {}, {}

    def __init__(self, args: ModelArguments, commands: list[Command]):
        """This model immediately submits. Useful for testing purposes"""
        super().__init__(args, commands)
        self._action_idx = 0

    def query(self, history: list[dict[str, str]]) -> str:
        # Need to at least do _something_ to submit
        if self._action_idx == 0:
            self._action_idx = 1
            action = "DISCUSSION\nLet's reproduce the bug by creating a `reproduce.py` file.\n\n```\ncreate reproduce.py\n```\n"
        elif self._action_idx == 1:
            self._action_idx = 0
            action = "DISCUSSION\nThe task should be resolved, so let's submit the patch.\n\n```\nsubmit\n```\n"
        self.update_stats(0, 0)
        return action


class VLLMModel(BaseModel):
    def _get_provider_configs(self, configs: dict) -> tuple[dict, dict]:
        return {}, {}

    def __init__(self, args: ModelArguments, commands: list[Command]):
        # Parse model name and host
        if ":" in args.model_name:
            # e.g. vllm:Qwen/Qwen3-32B
            _, model_name = args.model_name.split(":", 1)
        else:
            model_name = args.model_name
        
        # Create a new ModelArguments with the correct model_name, preserving other fields
        new_args = ModelArguments(
            model_name=model_name,
            per_instance_cost_limit=args.per_instance_cost_limit,
            total_cost_limit=args.total_cost_limit,
            temperature=args.temperature,
            top_p=args.top_p,
            top_k=args.top_k,
            replay_path=args.replay_path,
            host_url=args.host_url,
            per_instance_step_limit=args.per_instance_step_limit,
        )
        super().__init__(new_args, commands)
        self.vllm_model = model_name
        self.host_url = getattr(args, "host_url", "http://localhost:8000")
        if not self.host_url.startswith("http"):
            self.host_url = f"http://{self.host_url}"
        self.api_url = f"{self.host_url}/v1/chat/completions"

    def history_to_messages(self, history: list[dict[str, str]], is_demonstration: bool = False) -> list[dict[str, str]]:
        # Remove system messages if it is a demonstration
        if is_demonstration:
            history = [entry for entry in history if entry["role"] != "system"]
            return [{"role": entry["role"], "content": entry["content"]} for entry in history]
        return [{"role": entry["role"], "content": entry["content"]} for entry in history]

    def query(self, history: list[dict[str, str]]) -> str:
        payload = {
            "model": self.vllm_model,
            "messages": self.history_to_messages(history),
            "temperature": self.args.temperature,
            "top_p": self.args.top_p,
            "top_k": self.args.top_k,
        }
        try:
            response = requests.post(self.api_url, json=payload, timeout=3600)
            response.raise_for_status()
            data = response.json()
            # vLLM returns choices[0].message.content
            result = data["choices"][0]["message"]["content"]
            # Use token usage if available
            usage = data.get("usage", {})
            input_tokens = usage.get("prompt_tokens", 0)
            output_tokens = usage.get("completion_tokens", 0)
            self.update_stats(input_tokens, output_tokens)
            return clean_result(result)
        except Exception as e:
            logger.error(f"vLLM API error: {e}")
            raise


# ============================================================================
# Disabled provider helper functions (not used in VulRL)
# ============================================================================

if False:  # Disabled - only used by Anthropic/Bedrock models
    def anthropic_history_to_messages(model, history, is_demonstration=False):
        pass
    
    def anthropic_query(model, history):
        pass


def get_model(args: ModelArguments, commands: list[Command] | None = None):
    """
    Returns correct model object given arguments and commands.
    
    NOTE: VulRL worker_unit only supports OpenAI-compatible models.
    Non-OpenAI providers (Anthropic, Groq, Bedrock, Together, Ollama) are disabled.
    """
    if commands is None:
        commands = []
    
    # Load configurations to check shortcuts
    configs = load_model_configs()
    
    # Special models first (for testing/debugging)
    if args.model_name == "instant_empty_submit":
        return InstantEmptySubmitTestModel(args, commands)
    if args.model_name == "human":
        return HumanModel(args, commands)
    if args.model_name == "human_thought":
        return HumanThoughtModel(args, commands)
    if args.model_name == "replay":
        return ReplayModel(args, commands)
    
    # VulRL-specific: support vLLM models (OpenAI-compatible)
    if args.model_name.startswith("vllm:"):
        return VLLMModel(args, commands)
    
    # Support DeepSeek (OpenAI-compatible)
    if args.model_name.startswith("deepseek"):
        return DeepSeekModel(args, commands)
    
    # Check model prefixes for OpenAI
    if (args.model_name.startswith("gpt") or 
        args.model_name.startswith("ft:gpt") or 
        args.model_name.startswith("azure:gpt") or 
        args.model_name.startswith("o1") or
        args.model_name in configs.get('openai_shortcuts', {}) or
        args.model_name in configs.get('openai_models', {})):
        return OpenAIModel(args, commands)
    
    # Disabled providers (throw clear error)
    if (args.model_name.startswith("claude") or 
        args.model_name.startswith("bedrock") or 
        args.model_name.startswith("ollama") or
        args.model_name.startswith("groq") or
        args.model_name in configs.get('anthropic_shortcuts', {}) or
        args.model_name in configs.get('groq_shortcuts', {}) or
        args.model_name in configs.get('together_shortcuts', {})):
        raise ValueError(
            f"Model provider for '{args.model_name}' is not supported in VulRL worker_unit. "
            "Only OpenAI-compatible models are supported. "
            "Use vLLM, OpenAI, or other OpenAI-compatible endpoints."
        )
    
    # Default: treat as OpenAI-compatible (most inference servers use OpenAI format)
    logger.info(f"Treating unknown model '{args.model_name}' as OpenAI-compatible")
    return OpenAIModel(args, commands)
