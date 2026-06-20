"""Shared pytest fixtures."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from viral_editor.audio.beat_detector import AudioDspConfig


@pytest.fixture
def temp_artifacts_dir(tmp_path: Path) -> Path:
    """Isolated directory for model artifact round-trip tests."""
    return tmp_path / "temp"


def test_audio_config(**kwargs) -> AudioDspConfig:
    """AudioDspConfig with Demucs disabled for fast unit tests."""
    return AudioDspConfig(vocal_separation_enabled=False, **kwargs)


@pytest.fixture(autouse=True)
def disable_demucs_vocal_separation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip Demucs during analysis in the default test suite."""

    def _fake_vocal_activity(
        audio_path: Path,
        *,
        hop_length: int,
        sr: int,
        n_frames: int,
        mix_rms: np.ndarray | None = None,
        **kwargs: object,
    ) -> np.ndarray:
        del audio_path, hop_length, sr, mix_rms, kwargs
        return np.zeros(n_frames, dtype=np.float32)

    monkeypatch.setattr(
        "viral_editor.audio.beat_detector.compute_vocal_activity",
        _fake_vocal_activity,
    )
