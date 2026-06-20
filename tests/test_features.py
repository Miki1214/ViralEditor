"""Tests for beat-synchronous feature extraction."""

from __future__ import annotations

import numpy as np
import pytest

from viral_editor.audio.beat_tracker import BeatTrackResult
from viral_editor.audio.features import compute_beat_sync_features


def _synthetic_track(*, sr: int = 22050, duration_s: float = 12.0) -> np.ndarray:
    rng = np.random.default_rng(0)
    samples = int(sr * duration_s)
    t = np.linspace(0.0, duration_s, samples, endpoint=False)
    tone = 0.35 * np.sin(2 * np.pi * 220.0 * t)
    noise = 0.05 * rng.normal(size=samples)
    return (tone + noise).astype(np.float32)


def _beat_track(duration_s: float) -> BeatTrackResult:
    beat_times = np.arange(0.0, duration_s, 0.5, dtype=float)
    downbeats = beat_times[::4]
    return BeatTrackResult(
        engine="test",
        beat_times_s=beat_times,
        downbeat_times_s=downbeats,
        global_bpm=120.0,
    )


def test_parallel_and_serial_beat_sync_features_match() -> None:
    sr = 22050
    y = _synthetic_track(sr=sr, duration_s=12.0)
    beat_track = _beat_track(12.0)
    stft_power = np.abs(
        __import__("librosa").stft(y, n_fft=2048, hop_length=512)
    ) ** 2

    serial = compute_beat_sync_features(
        y,
        sr,
        beat_track,
        stft_power=stft_power,
        max_workers=1,
    )
    parallel = compute_beat_sync_features(
        y,
        sr,
        beat_track,
        stft_power=stft_power,
        max_workers=4,
    )

    assert serial.meta.key == parallel.meta.key
    assert serial.meta.n_beats == parallel.meta.n_beats
    np.testing.assert_allclose(serial.chroma_sync, parallel.chroma_sync, rtol=1e-5, atol=1e-5)
    np.testing.assert_allclose(serial.mfcc_sync, parallel.mfcc_sync, rtol=1e-4, atol=1e-3)
    np.testing.assert_allclose(serial.rms_sync, parallel.rms_sync, rtol=1e-5, atol=1e-5)
    np.testing.assert_allclose(serial.contrast_sync, parallel.contrast_sync, rtol=1e-4, atol=1e-3)
    np.testing.assert_allclose(serial.tonnetz_sync, parallel.tonnetz_sync, rtol=1e-4, atol=1e-3)


def test_beat_sync_features_shapes() -> None:
    sr = 22050
    duration_s = 6.0
    y = _synthetic_track(sr=sr, duration_s=duration_s)
    beat_track = _beat_track(duration_s)

    features = compute_beat_sync_features(y, sr, beat_track, max_workers=2)
    n_beats = beat_track.beat_times_s.size

    assert features.chroma_sync.shape == (12, n_beats)
    assert features.mfcc_sync.shape[1] == n_beats
    assert features.rms_sync.shape[1] == n_beats
    assert features.contrast_sync.shape[1] == n_beats
    assert features.tonnetz_sync.shape[1] == n_beats
