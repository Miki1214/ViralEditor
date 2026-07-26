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
    orientation_enabled: bool = True
    orientation_model_repo: str = "DuarteBarbosa/deep-image-orientation-detection"
    orientation_model_file: str = "orientation_model_v2_0.9882.onnx"
    keyframe_count: int = 3
    min_orientation_confidence: float = 0.55


@lru_cache(maxsize=1)
def load_auto_rotate_settings() -> AutoRotateSettings:
    """Load auto-rotation settings from environment variables."""
    return AutoRotateSettings(
        enabled=_env_bool("AUTO_ROTATE_ENABLED", True),
        orientation_enabled=_env_bool("AUTO_ROTATE_ORIENTATION_ENABLED", True),
        orientation_model_repo=os.environ.get(
            "ORIENTATION_MODEL_REPO",
            "DuarteBarbosa/deep-image-orientation-detection",
        ),
        orientation_model_file=os.environ.get(
            "ORIENTATION_MODEL_FILE",
            "orientation_model_v2_0.9882.onnx",
        ),
        keyframe_count=_env_int("AUTO_ROTATE_KEYFRAME_COUNT", 3),
        min_orientation_confidence=_env_float(
            "AUTO_ROTATE_MIN_ORIENTATION_CONFIDENCE",
            0.55,
        ),
    )
