"""Configuration loader for Worker Router."""

import yaml
from pathlib import Path
from typing import Any, Dict
from dotenv import load_dotenv
import os


class Config:
    """Configuration manager."""
    
    def __init__(self, config_path: str = "config.yaml"):
        """Load configuration from YAML and environment variables.
        
        Args:
            config_path: Path to config.yaml file
        """
        # Load .env file
        load_dotenv()
        
        # Load YAML config
        config_file = Path(config_path)
        with open(config_file, 'r') as f:
            self._config: Dict[str, Any] = yaml.safe_load(f)
        
        # Override with environment variables if present
        self._apply_env_overrides()
    
    def _apply_env_overrides(self):
        """Apply environment variable overrides."""
        # Redis password from .env
        redis_password = os.getenv("REDIS_PASSWORD")
        if redis_password:
            self._config["redis"]["password"] = redis_password
        
        # Optional overrides
        if os.getenv("REDIS_HOST"):
            self._config["redis"]["host"] = os.getenv("REDIS_HOST")
        if os.getenv("REDIS_PORT"):
            self._config["redis"]["port"] = int(os.getenv("REDIS_PORT"))
        if os.getenv("WORKER_ROUTER_PORT"):
            self._config["worker_router"]["port"] = int(os.getenv("WORKER_ROUTER_PORT"))
        if os.getenv("LLM_ENDPOINT"):
            self._config["llm"]["default_endpoint"] = os.getenv("LLM_ENDPOINT")
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """Get config value by dot-separated key path.
        
        Args:
            key_path: Dot-separated key path (e.g., "redis.host")
            default: Default value if key not found
            
        Returns:
            Config value
        """
        keys = key_path.split(".")
        value = self._config
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value
    
    @property
    def worker_router(self) -> Dict[str, Any]:
        """Get worker_router config section."""
        return self._config.get("worker_router", {})
    
    @property
    def redis(self) -> Dict[str, Any]:
        """Get redis config section."""
        return self._config.get("redis", {})
    
    @property
    def llm(self) -> Dict[str, Any]:
        """Get llm config section."""
        return self._config.get("llm", {})
    
    @property
    def docker(self) -> Dict[str, Any]:
        """Get docker config section."""
        return self._config.get("docker", {})
    
    @property
    def logging(self) -> Dict[str, Any]:
        """Get logging config section."""
        return self._config.get("logging", {})


# Global config instance
config = Config()
