"""
VulRL Progress Reward Module (v2.3 taxonomy)

Per-mechanism progress reward functions implementing the Φ formula:
    R(τ) = 1.0                              if oracle_test passes
         = score_primary(τ)                 otherwise

Each mechanism module exports:
    compute_<MXX>_progress(trajectory, **opts) -> (score, debug_info)

where score ∈ {0, 0.05, 0.10, 0.12, 0.15, 0.20}.

This is the Phase B follow-up: validating M05/M10/M03 (the 3 highest-coverage
mechanisms covering 39/67 = 58% of cases) before extending to all 11 active
mechanisms.
"""

from .dispatcher import ProgressDispatcher
from .m01_sql_injection import compute_m01_progress
from .m03_path_traversal import compute_m03_progress
from .m04_xxe import compute_m04_progress
from .m05_engine_injection import compute_m05_progress
from .m06_cmd_injection import compute_m06_progress
from .m07_deserialization import compute_m07_progress
from .m08_upload_then_access import compute_m08_progress
from .m09_auth_bypass_chain import compute_m09_progress
from .m10_config_abuse import compute_m10_progress
from .m11_non_http_protocol import compute_m11_progress

__all__ = [
    "ProgressDispatcher",
    "compute_m01_progress",
    "compute_m03_progress",
    "compute_m04_progress",
    "compute_m05_progress",
    "compute_m06_progress",
    "compute_m07_progress",
    "compute_m08_progress",
    "compute_m09_progress",
    "compute_m10_progress",
    "compute_m11_progress",
]
