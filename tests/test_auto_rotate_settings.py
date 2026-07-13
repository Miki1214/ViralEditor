"""Tests for auto-rotation environment settings."""

from __future__ import annotations

from viral_editor.auto_rotate_settings import load_auto_rotate_settings


def test_load_auto_rotate_settings_reads_env_overrides(monkeypatch) -> None:
    load_auto_rotate_settings.cache_clear()
    monkeypatch.setenv("AUTO_ROTATE_ENABLED", "false")
    monkeypatch.setenv("AUTO_ROTATE_ORIENTATION_ENABLED", "false")
    monkeypatch.setenv("ORIENTATION_MODEL_REPO", "DuarteBarbosa/deep-image-orientation-detection")
    monkeypatch.setenv("ORIENTATION_MODEL_FILE", "orientation_model_v2_0.9882.onnx")
    monkeypatch.setenv("AUTO_ROTATE_KEYFRAME_COUNT", "5")
    monkeypatch.setenv("AUTO_ROTATE_MIN_ORIENTATION_CONFIDENCE", "0.7")

    settings = load_auto_rotate_settings()

    assert settings.enabled is False
    assert settings.orientation_enabled is False
    assert settings.orientation_model_repo == "DuarteBarbosa/deep-image-orientation-detection"
    assert settings.orientation_model_file == "orientation_model_v2_0.9882.onnx"
    assert settings.keyframe_count == 5
    assert settings.min_orientation_confidence == 0.7

    load_auto_rotate_settings.cache_clear()
