"""Structured logging helpers."""

from __future__ import annotations

import logging
from typing import Literal

from rich.logging import RichHandler

_VERBOSE = False
_CONFIGURED = False

StageAction = Literal["start", "complete", "skip"]


def configure_logging(*, verbose: bool = False) -> None:
    """Configure root logging once per process."""
    global _VERBOSE, _CONFIGURED
    _VERBOSE = verbose

    if _CONFIGURED:
        logging.getLogger().setLevel(logging.DEBUG if verbose else logging.INFO)
        return

    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, show_path=verbose)],
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger (call ``configure_logging`` from the CLI first)."""
    return logging.getLogger(name)


def log_stage(stage: str, *, action: StageAction = "start") -> None:
    """Emit a uniform stage boundary log line."""
    logger = get_logger("viral_editor.pipeline")
    labels = {
        "start": "Starting",
        "complete": "Completed",
        "skip": "Skipping",
    }
    logger.info("%s stage: %s", labels[action], stage)
