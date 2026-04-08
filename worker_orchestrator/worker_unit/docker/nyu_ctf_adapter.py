"""NYU CTF (ctfmix/nyu_ctf) Docker adapter."""

from __future__ import annotations

from typing import Any, Dict

from .ctfmix_docker_base import CTFMixDockerAdapterBase


class NYUCTFAdapter(CTFMixDockerAdapterBase):
    """Compose-backed NYU tasks under benchmark/ctfmix/nyu_ctf/."""

    ADAPTER_LABEL = "NYUCTFAdapter"

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
