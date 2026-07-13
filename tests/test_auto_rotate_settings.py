"""Tests for auto-rotation environment settings."""

from __future__ import annotations

import os

from viral_editor.auto_rotate_settings import load_auto_rotate_settings


def test_load_auto_rotate_settings_reads_env_overrides(
    monkeypatch,
) -> None:
    load_auto_rotate_settings.cache_clear()
    monkeypatch.setenv("AUTO_ROTATE_ENABLED", "false")
    monkeypatch.setenv("OLLAMA_HOST", "http://127.0.0.1:11435")
    monkeypatch.setenv("OLLAMA_MODEL", "bakllava")
    monkeypatch.setenv("OLLAMA_VISION_TIMEOUT_S", "9")
    monkeypatch.setenv("AUTO_ROTATE_KEYFRAME_COUNT", "5")

    settings = load_auto_rotate_settings()

    assert settings.enabled is False
    assert settings.ollama_host == "http://127.0.0.1:11435"
    assert settings.ollama_model == "bakllava"
    assert settings.vision_timeout_s == 9.0
    assert settings.keyframe_count == 5

    load_auto_rotate_settings.cache_clear()
