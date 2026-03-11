"""
EzVulRL Generator - HTTP-based generator for VulRL using Worker Router.

This generator delegates rollout execution to the Worker Router API,
which manages a pool of worker units that execute vulnerability exploitation tasks.
"""

from .ez_vulrl_generator import EzVulRLGenerator
from .worker_router_client import WorkerRouterClient

__all__ = ["EzVulRLGenerator", "WorkerRouterClient"]
