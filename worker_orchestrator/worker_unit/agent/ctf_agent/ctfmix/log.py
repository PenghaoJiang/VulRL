"""Logging helpers kept close to enigma-plus behaviour."""

from __future__ import annotations

import logging
import os
from pathlib import PurePath

from rich.logging import RichHandler

_SET_UP_LOGGERS: set[str] = set()
_ADDITIONAL_HANDLERS: list[logging.Handler] = []

logging.TRACE = 5  # type: ignore[attr-defined]
logging.addLevelName(logging.TRACE, "TRACE")  # type: ignore[attr-defined]


def _interpret_level_from_env(level: str | None, *, default: int = logging.DEBUG) -> int:
    if not level:
        return default
    if level.isnumeric():
        return int(level)
    return getattr(logging, level.upper())


_STREAM_LEVEL = _interpret_level_from_env(os.environ.get("SWE_AGENT_LOG_STREAM_LEVEL"))
_FILE_LEVEL = _interpret_level_from_env(os.environ.get("SWE_AGENT_LOG_FILE_LEVEL"), default=logging.TRACE)  # type: ignore[arg-type]


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if name in _SET_UP_LOGGERS:
        return logger
    handler = RichHandler(show_time=bool(os.environ.get("SWE_AGENT_LOG_TIME", False)), show_path=False)
    handler.setLevel(_STREAM_LEVEL)
    logger.setLevel(min(_STREAM_LEVEL, _FILE_LEVEL))
    logger.addHandler(handler)
    logger.propagate = False
    _SET_UP_LOGGERS.add(name)
    for extra_handler in _ADDITIONAL_HANDLERS:
        logger.addHandler(extra_handler)
    return logger


def add_file_handler(path: PurePath | str) -> None:
    handler = logging.FileHandler(path)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    handler.setLevel(_FILE_LEVEL)
    for name in _SET_UP_LOGGERS:
        logging.getLogger(name).addHandler(handler)
    _ADDITIONAL_HANDLERS.append(handler)


default_logger = get_logger("ctfmix")
