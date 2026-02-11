"""Environment adapter registry and factory."""

from typing import Dict, Any, Type
from vulrl.docker.base import BaseEnvAdapter


class EnvRegistry:
    """Factory for creating environment adapters based on task type."""
    
    _adapters: Dict[str, Type[BaseEnvAdapter]] = {}
    
    @classmethod
    def register(cls, task_type: str, adapter_class: Type[BaseEnvAdapter]) -> None:
        """
        Register an adapter class for a task type.
        
        Args:
            task_type: Type of task (cvebench, vulhub, xbow)
            adapter_class: Adapter class to register
        """
        cls._adapters[task_type.lower()] = adapter_class
        print(f"[EnvRegistry] Registered adapter: {task_type} -> {adapter_class.__name__}")
    
    @classmethod
    def create(cls, config: Dict[str, Any]) -> BaseEnvAdapter:
        """
        Create an adapter instance based on task type.
        
        Args:
            config: Configuration dict containing 'task_type' key
            
        Returns:
            Adapter instance
            
        Raises:
            ValueError: If task_type is not registered
        """
        task_type = config.get('task_type', '').lower()
        
        if not task_type:
            raise ValueError("Config must contain 'task_type' key")
        
        if task_type not in cls._adapters:
            available = ', '.join(cls._adapters.keys())
            raise ValueError(
                f"Unknown task type: {task_type}. "
                f"Available types: {available}"
            )
        
        adapter_class = cls._adapters[task_type]
        print(f"[EnvRegistry] Creating adapter: {adapter_class.__name__} for task {config.get('task_id', 'unknown')}")
        
        return adapter_class(config)
    
    @classmethod
    def list_adapters(cls) -> Dict[str, Type[BaseEnvAdapter]]:
        """
        Get all registered adapters.
        
        Returns:
            Dictionary of task_type -> adapter_class
        """
        return cls._adapters.copy()


# Auto-register known adapters
def _register_default_adapters():
    """Register default adapters on module import."""
    try:
        from vulrl.docker.adapters import CVEBenchAdapter, VulhubAdapter, XbowAdapter
        
        EnvRegistry.register('cvebench', CVEBenchAdapter)
        EnvRegistry.register('vulhub', VulhubAdapter)
        EnvRegistry.register('xbow', XbowAdapter)
        
    except ImportError as e:
        print(f"[EnvRegistry] Warning: Could not register some adapters: {e}")


# Auto-register on import
_register_default_adapters()
