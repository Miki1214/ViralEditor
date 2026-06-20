"""Tests for Demucs vocal separation and vocal activity lane."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest

from viral_editor.audio.vocal_separation import (
    VOCAL_STEM_SHARE_MIN,
    compute_vocal_activity,
    separate_vocal_stem,
)

_VOCAL_SHARES = {"drums": 0.2, "bass": 0.2, "other": 0.2, "vocals": 0.4}


def test_compute_vocal_activity_aligns_and_normalizes() -> None:
    sr = 22050
    hop_length = 512
    n_frames = 120
    vocal = np.zeros(sr * 2, dtype=np.float32)
    vocal[sr // 2 : sr] = 0.8
    mix_rms = np.full(n_frames, 0.12, dtype=np.float32)

    with patch(
        "viral_editor.audio.vocal_separation.separate_vocal_stem",
        return_value=(vocal, sr, _VOCAL_SHARES),
    ):
        activity = compute_vocal_activity(
            Path("unused.wav"),
            hop_length=hop_length,
            sr=sr,
            n_frames=n_frames,
            mix_rms=mix_rms,
        )

    assert activity.shape == (n_frames,)
    assert activity.dtype == np.float32
    assert float(activity.max()) == pytest.approx(1.0, abs=1e-5)
    assert float(activity.min()) >= 0.0
    assert float(activity[30:70].mean()) > float(activity[:10].mean())


def test_compute_vocal_activity_flat_when_vocal_share_low() -> None:
    sr = 22050
    hop_length = 512
    n_frames = 80
    vocal = np.random.default_rng(0).normal(0, 0.4, sr).astype(np.float32)
    low_share = {"drums": 0.4, "bass": 0.3, "other": 0.25, "vocals": 0.05}

    with patch(
        "viral_editor.audio.vocal_separation.separate_vocal_stem",
        return_value=(vocal, sr, low_share),
    ):
        activity = compute_vocal_activity(
            Path("unused.wav"),
            hop_length=hop_length,
            sr=sr,
            n_frames=n_frames,
            mix_rms=np.full(n_frames, 0.1, dtype=np.float32),
        )

    assert activity.shape == (n_frames,)
    assert float(activity.max()) == 0.0
    assert float(low_share["vocals"]) < VOCAL_STEM_SHARE_MIN


def test_compute_vocal_activity_interpolates_to_n_frames() -> None:
    sr = 22050
    hop_length = 512
    vocal = np.random.default_rng(1).normal(0, 0.3, sr * 3).astype(np.float32)

    with patch(
        "viral_editor.audio.vocal_separation.separate_vocal_stem",
        return_value=(vocal, sr, _VOCAL_SHARES),
    ):
        activity = compute_vocal_activity(
            Path("unused.wav"),
            hop_length=hop_length,
            sr=sr,
            n_frames=500,
            target_samples=sr * 3,
            frame_length=2048,
            mix_rms=np.full(500, 0.08, dtype=np.float32),
        )

    assert activity.shape == (500,)
    assert float(activity.max()) > 0.1


def test_compute_vocal_activity_resamples_model_sr() -> None:
    model_sr = 44100
    analysis_sr = 22050
    hop_length = 512
    n_frames = 80
    vocal = np.random.default_rng(0).normal(0, 0.2, model_sr).astype(np.float32)

    with patch(
        "viral_editor.audio.vocal_separation.separate_vocal_stem",
        return_value=(vocal, model_sr, _VOCAL_SHARES),
    ):
        activity = compute_vocal_activity(
            Path("unused.wav"),
            hop_length=hop_length,
            sr=analysis_sr,
            n_frames=n_frames,
            mix_rms=np.full(n_frames, 0.1, dtype=np.float32),
        )

    assert activity.shape == (n_frames,)
    assert float(activity.max()) <= 1.0 + 1e-6


@pytest.mark.integration
@pytest.mark.skipif(
    not Path(__file__).resolve().parents[1].joinpath("fixtures/audio/validation_clicks.wav").is_file(),
    reason="fixture missing",
)
def test_separate_vocal_stem_integration() -> None:
    if not __import__("os").environ.get("RUN_DEMUCS_INTEGRATION"):
        pytest.skip("Set RUN_DEMUCS_INTEGRATION=1 to run Demucs integration test")

    fixture = Path(__file__).resolve().parents[1] / "fixtures" / "audio" / "validation_clicks.wav"
    vocal, sr, shares = separate_vocal_stem(fixture)
    assert vocal.ndim == 1
    assert vocal.size > 0
    assert sr == 44100
    assert "vocals" in shares


def test_separate_vocal_stem_keeps_librosa_channel_first_layout(tmp_path: Path) -> None:
    """librosa stereo is (channels, samples); must not transpose before Demucs."""
    captured: dict[str, object] = {}
    audio_path = tmp_path / "stereo.wav"
    audio_path.write_bytes(b"\x00")

    def _fake_load(path: str, *, sr: int | None, mono: bool) -> tuple[np.ndarray, int]:
        del path, sr, mono
        return np.random.default_rng(0).normal(0, 0.2, (2, 8000)).astype(np.float32), 44100

    def _fake_convert(wav, in_sr, out_sr, channels):
        captured["shape"] = tuple(wav.shape)
        return wav

    with (
        patch("viral_editor.audio.vocal_separation.librosa.load", side_effect=_fake_load),
        patch("viral_editor.audio.vocal_separation.get_model") as mock_get_model,
        patch("viral_editor.audio.vocal_separation.convert_audio", side_effect=_fake_convert),
        patch("viral_editor.audio.vocal_separation.apply_model") as mock_apply,
    ):
        mock_model = mock_get_model.return_value
        mock_model.sources = ["drums", "bass", "other", "vocals"]
        mock_model.samplerate = 44100
        mock_model.audio_channels = 2
        mock_apply.return_value = [
            __import__("torch").zeros(4, 2, 8000),
        ]

        separate_vocal_stem(audio_path)

    assert captured["shape"] == (2, 8000)


def test_vocal_lane_flat_for_instrumental_fixture(tmp_path: Path) -> None:
    from viral_editor.audio.beat_detector import analyze_audio_with_envelope

    sr = 22050
    duration_s = 2.0
    y = np.random.default_rng(2).normal(0, 0.05, int(sr * duration_s)).astype(np.float32)
    y[int(sr * 0.5) : int(sr * 0.5) + 800] += 0.4
    wav = tmp_path / "mid.wav"
    import soundfile as sf

    sf.write(wav, y, sr)

    low_share = {"drums": 0.5, "bass": 0.25, "other": 0.2, "vocals": 0.05}
    with patch(
        "viral_editor.audio.vocal_separation.separate_vocal_stem",
        return_value=(np.zeros(int(sr * duration_s), dtype=np.float32), sr, low_share),
    ):
        result = analyze_audio_with_envelope(wav)

    vocal = result.scope_lanes.get("vocal")
    assert vocal is not None
    assert float(vocal.max()) == 0.0
