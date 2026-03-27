"""VulRL v4 - Reinforcement Learning for Vulnerability Exploitation."""

__version__ = "4.0.0"

__all__ = ["EnvRegistry", "RewardRouter", "SecurityEnv"]


def __getattr__(name: str):
    if name in {"SecurityEnv", "EnvRegistry"}:
        from .env import EnvRegistry, SecurityEnv

        exports = {
            "EnvRegistry": EnvRegistry,
            "SecurityEnv": SecurityEnv,
        }
        return exports[name]
    if name == "RewardRouter":
        from .reward import RewardRouter

        return RewardRouter
    raise AttributeError(name)
