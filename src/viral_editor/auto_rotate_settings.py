"""Environment-driven settings for auto-rotation on upload."""

from __future__ import annotations

import os
from functools import lru_cache

from viral_editor.models import DomainModel


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return float(raw)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return int(raw)


class AutoRotateSettings(DomainModel):
    """Deployment settings for the upload auto-rotation pipeline."""

    enabled: bool = True
    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llava"
    vision_timeout_s: float = 6.0
    keyframe_count: int = 3
    min_vision_confidence: float = 0.55


@lru_cache(maxsize=1)
def load_auto_rotate_settings() -> AutoRotateSettings:
    """Load auto-rotation settings from environment variables."""
    return AutoRotateSettings(
        enabled=_env_bool("AUTO_ROTATE_ENABLED", True),
        ollama_host=os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "llava"),
        vision_timeout_s=_env_float("OLLAMA_VISION_TIMEOUT_S", 6.0),
        keyframe_count=_env_int("AUTO_ROTATE_KEYFRAME_COUNT", 3),
        min_vision_confidence=_env_float("AUTO_ROTATE_MIN_VISION_CONFIDENCE", 0.55),
    )
