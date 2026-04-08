"""Cybench Docker-only adapter (skips non-ctfnet / auxiliary compose bundles)."""

from __future__ import annotations

from typing import Any, Dict, FrozenSet

from .ctfmix_docker_base import CTFMixDockerAdapterBase


# Excluded from automated bring-up (see ctfmix inventory): shared_net / non-ctfnet aux compose.
CYBENCH_SKIP_REL_PATHS: FrozenSet[str] = frozenset(
    {
        "cybench/S23/pwn/network-tools/challenge",
        "cybench/HKC/web/05-motp/public",
    }
)


class CybenchDockerAdapter(CTFMixDockerAdapterBase):
    """Compose-backed Cybench tasks under benchmark/ctfmix/cybench/."""

    ADAPTER_LABEL = "CybenchDockerAdapter"
    CYBENCH_SKIP_REL_PATHS = CYBENCH_SKIP_REL_PATHS

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
