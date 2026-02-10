"""
Environment Adapter Registry

Centralized registry for managing and creating environment adapters.
"""

from typing import Dict, Type, Any
from .base import BaseEnvAdapter, StandardEnvConfig
from .adapters import VulhubAdapter, CveBenchAdapter, XbowAdapter


class EnvRegistry:
    """
    Environment adapter registry
    
    Manages adapter registration and creation
    """
    
    # Built-in adapters
    ADAPTERS: Dict[str, Type[BaseEnvAdapter]] = {
        "vulhub": VulhubAdapter,
        "cvebench": CveBenchAdapter,
        "cve-bench": CveBenchAdapter,  # Alias
        "ctf": CveBenchAdapter,  # Alias
        "xbow": XbowAdapter,
    }
    
    @classmethod
    def create_adapter(cls, config: StandardEnvConfig) -> BaseEnvAdapter:
        """
        Create adapter instance from config
        
        Args:
            config: Standardized environment configuration
            
        Returns:
            Adapter instance
            
        Raises:
            ValueError: If task_type is not registered
        """
        task_type = config.task_type.lower()
        
        if task_type not in cls.ADAPTERS:
            raise ValueError(
                f"Unknown task type: {task_type}. "
                f"Available: {list(cls.ADAPTERS.keys())}"
            )
        
        # Prepare adapter configuration
        adapter_config = {
            "task_id": config.task_id,
            "task_type": config.task_type,
            "max_steps": config.max_steps,
            "timeout": config.timeout,
            "target_host": config.target_host,
            "target_port": config.target_port,
            "target_protocol": config.target_protocol,
            **config.backend_config  # Backend-specific configuration
        }
        
        # Create adapter instance
        adapter_class = cls.ADAPTERS[task_type]
        adapter = adapter_class(adapter_config)
        
        # Start backend environment
        adapter.setup()
        
        return adapter
    
    @classmethod
    def register(cls, task_type: str, adapter_class: Type[BaseEnvAdapter]):
        """
        Register a new adapter
        
        Args:
            task_type: Task type identifier (e.g., "custom")
            adapter_class: Adapter class (must inherit from BaseEnvAdapter)
            
        Example:
            EnvRegistry.register("custom", MyCustomAdapter)
        """
        if not issubclass(adapter_class, BaseEnvAdapter):
            raise TypeError(f"{adapter_class} must inherit from BaseEnvAdapter")
        
        cls.ADAPTERS[task_type.lower()] = adapter_class
        print(f"[EnvRegistry] Registered adapter: {task_type} -> {adapter_class.__name__}")
    
    @classmethod
    def list_adapters(cls) -> list:
        """
        List all registered adapters
        
        Returns:
            List of registered task types
        """
        return list(cls.ADAPTERS.keys())
    
    @classmethod
    def get_adapter_class(cls, task_type: str) -> Type[BaseEnvAdapter]:
        """
        Get adapter class by task type
        
        Args:
            task_type: Task type identifier
            
        Returns:
            Adapter class
            
        Raises:
            ValueError: If task_type is not registered
        """
        task_type = task_type.lower()
        if task_type not in cls.ADAPTERS:
            raise ValueError(
                f"Unknown task type: {task_type}. "
                f"Available: {list(cls.ADAPTERS.keys())}"
            )
        return cls.ADAPTERS[task_type]
