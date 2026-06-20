"""Tests for audio beat/transient detection."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from viral_editor.audio.beat_detector import (
    AudioDspConfig,
    analyze_audio,
    analyze_audio_with_envelope,
    fold_tempo,
)


def _write_wav(path: Path, y: np.ndarray, sr: int = 22050) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, y, sr)
    return path


def _click_track(
    *,
    sr: int = 22050,
    interval_s: float = 0.5,
    duration_s: float = 5.0,
    amplitude: float = 1.0,
    start_s: float = 0.5,
) -> np.ndarray:
    samples = int(sr * duration_s)
    y = np.zeros(samples, dtype=np.float32)
    t = start_s
    while t < duration_s:
        index = int(t * sr)
        end = min(index + 8, samples)
        y[index:end] = amplitude
        t += interval_s
    return y


def test_fold_tempo_halves_and_doubles() -> None:
    assert fold_tempo(30.0) == pytest.approx(60.0)
    assert fold_tempo(360.0) == pytest.approx(180.0)
    assert fold_tempo(120.0) == pytest.approx(120.0)


def test_click_track_onsets_within_tolerance(tmp_path: Path) -> None:
    sr = 22050
    y = _click_track(sr=sr, interval_s=0.5, duration_s=5.0)
    wav = _write_wav(tmp_path / "clicks.wav", y, sr)

    timeline = analyze_audio(wav, config=AudioDspConfig(dedupe_window_ms=30))

    assert len(timeline.transients) >= 8
    expected_ms = [int(round(t * 1000)) for t in np.arange(0.5, 5.0, 0.5)]
    for expected in expected_ms:
        assert any(abs(t.timestamp_ms - expected) <= 80 for t in timeline.transients)


def test_metronome_bpm_near_120(tmp_path: Path) -> None:
    sr = 22050
    # 120 BPM -> 0.5 s between beats
    y = _click_track(sr=sr, interval_s=0.5, duration_s=8.0)
    wav = _write_wav(tmp_path / "metro.wav", y, sr)

    timeline = analyze_audio(wav)

    assert timeline.global_bpm == pytest.approx(120.0, rel=0.15)


def test_drop_classification_on_loud_hit(tmp_path: Path) -> None:
    sr = 22050
    duration_s = 4.0
    y = np.random.default_rng(0).normal(0, 0.01, int(sr * duration_s)).astype(np.float32)

    # Quiet ticks
    for t in (0.5, 1.0, 1.5):
        y[int(t * sr)] = 0.15

    # Loud drop hit
    drop_index = int(2.5 * sr)
    y[drop_index : drop_index + 3] = 1.0

    wav = _write_wav(tmp_path / "drop.wav", y, sr)
    timeline = analyze_audio(
        wav,
        config=AudioDspConfig(drop_percentile=0.85, min_drop_gap_ms=800),
    )

    drops = [t for t in timeline.transients if t.type == "drop"]
    assert drops
    assert any(abs(d.timestamp_ms - 2500) <= 120 for d in drops)
    assert max(d.amplitude_normalized for d in drops) >= 0.9


def test_analyze_audio_is_deterministic(tmp_path: Path) -> None:
    y = _click_track(duration_s=3.0)
    wav = _write_wav(tmp_path / "deterministic.wav", y)

    first = analyze_audio(wav)
    second = analyze_audio(wav)

    assert first == second


def test_analyze_audio_with_envelope_writes_npy(tmp_path: Path) -> None:
    y = _click_track(duration_s=2.0)
    wav = _write_wav(tmp_path / "envelope.wav", y)

    result = analyze_audio_with_envelope(wav)

    assert result.onset_envelope.ndim == 1
    assert result.onset_envelope.size > 0
    assert result.chroma.ndim == 2
    assert result.chroma.shape[0] == 12
    assert result.timeline.sample_rate == 22050
    assert result.timeline.audio_duration_seconds == pytest.approx(2.0, abs=0.1)
    assert result.beat_features.meta.engine in {"librosa", "beat-this"}
    assert result.beat_features.chroma_sync.ndim == 2
    assert result.beat_features.chroma_sync.shape[1] == result.beat_features.meta.n_beats
    assert set(result.scope_lanes.keys()) >= {
        "rms",
        "band_low",
        "band_mid",
        "band_high",
        "build",
        "drop_salience",
        "flux_low",
        "flux_high",
        "pacing_density",
        "vocal",
    }
    for lane in result.scope_lanes.values():
        assert lane.ndim == 1
        assert lane.size > 0


def test_downbeats_are_subset_of_beats(tmp_path: Path) -> None:
    y = _click_track(duration_s=4.0)
    wav = _write_wav(tmp_path / "downbeats.wav", y)
    result = analyze_audio_with_envelope(wav)
    beats = set(round(float(t), 4) for t in result.beat_features.beat_times_s)
    for downbeat in result.beat_features.downbeat_times_s:
        assert round(float(downbeat), 4) in beats


def test_beat_sync_feature_shapes(tmp_path: Path) -> None:
    y = _click_track(duration_s=3.0)
    wav = _write_wav(tmp_path / "features.wav", y)
    result = analyze_audio_with_envelope(wav)
    n_beats = result.beat_features.meta.n_beats
    assert result.beat_features.mfcc_sync.shape == (13, n_beats)
    assert result.beat_features.rms_sync.shape[1] == n_beats
    assert result.beat_features.contrast_sync.shape[1] == n_beats
    assert result.beat_features.tonnetz_sync.shape[1] == n_beats


def test_timeline_schema_fields(tmp_path: Path) -> None:
    y = _click_track(duration_s=2.0)
    wav = _write_wav(tmp_path / "schema.wav", y)

    timeline = analyze_audio(wav)

    assert timeline.global_bpm > 0
    assert timeline.sample_rate == 22050
    assert timeline.audio_duration_seconds > 0
    for transient in timeline.transients:
        assert transient.timestamp_ms >= 0
        assert 0.0 <= transient.amplitude_normalized <= 1.0
        assert transient.type in {"percussive", "bass", "drop"}
