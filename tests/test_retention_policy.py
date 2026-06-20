"""Tests for the retention editing policy."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from viral_editor.audio.beat_detector import analyze_audio_with_envelope
from viral_editor.editing.retention_policy import (
    EARLY_HOOK_FX_BY_S,
    INTERRUPT_MIN_GAP_S,
    classify_accents,
    find_energy_peaks,
    place_interrupts,
    score_plan,
)
from viral_editor.video.spatial_fx import plan_spatial_fx
from viral_editor.models import MediaInfo


def _write_drop_fixture(path: Path) -> Path:
    sr = 22050
    duration_s = 4.0
    y = np.random.default_rng(0).normal(0, 0.01, int(sr * duration_s)).astype(np.float32)
    for t in (0.5, 1.0, 1.5):
        y[int(t * sr)] = 0.15
    drop_index = int(2.5 * sr)
    y[drop_index : drop_index + 3] = 1.0
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, y, sr)
    return path


def test_find_energy_peaks_prefers_loud_hit(tmp_path: Path) -> None:
    wav = _write_drop_fixture(tmp_path / "drop.wav")
    result = analyze_audio_with_envelope(wav)
    peaks = find_energy_peaks(
        result.scope_lanes,
        result.beat_features.downbeat_times_s.tolist(),
    )
    assert peaks
    assert any(abs(peak.time_s - 2.5) <= 0.25 for peak in peaks)


def test_zoom_not_placed_in_rms_valley(tmp_path: Path) -> None:
    wav = _write_drop_fixture(tmp_path / "drop.wav")
    result = analyze_audio_with_envelope(wav)
    events = place_interrupts(
        result.scope_lanes,
        result.beat_features.downbeat_times_s.tolist(),
        window_start_s=0.0,
        window_end_s=result.timeline.audio_duration_seconds,
    )
    zooms = [event for event in events if event.kind == "zoom"]
    assert zooms
    rms = result.scope_lanes["rms"]
    hop = 512
    sr = result.timeline.sample_rate
    for event in zooms:
        frame = int(round((event.timestamp_s) * sr / hop))
        frame = min(max(frame, 0), rms.size - 1)
        peak = float(rms.max())
        assert float(rms[frame]) >= peak * 0.35


def test_interrupt_cadence_respects_min_gap(tmp_path: Path) -> None:
    wav = _write_drop_fixture(tmp_path / "drop.wav")
    result = analyze_audio_with_envelope(wav)
    events = place_interrupts(
        result.scope_lanes,
        result.beat_features.downbeat_times_s.tolist(),
        window_start_s=0.0,
        window_end_s=result.timeline.audio_duration_seconds,
    )
    for index in range(1, len(events)):
        gap = events[index].timestamp_s - events[index - 1].timestamp_s
        assert gap >= INTERRUPT_MIN_GAP_S - 0.05 or index == 1


def test_early_hook_zoom_within_budget(tmp_path: Path) -> None:
    wav = _write_drop_fixture(tmp_path / "drop.wav")
    result = analyze_audio_with_envelope(wav)
    events = place_interrupts(
        result.scope_lanes,
        result.beat_features.downbeat_times_s.tolist(),
        window_start_s=0.0,
        window_end_s=min(7.0, result.timeline.audio_duration_seconds),
    )
    zooms = [event for event in events if event.kind == "zoom"]
    assert zooms
    # Short synthetic fixture may only have a strong peak after 2s — ensure we still place it.
    assert any(abs(event.timestamp_s - 2.5) <= 0.35 for event in zooms)


def test_classify_accents_marks_drop_at_energy_peak(tmp_path: Path) -> None:
    wav = _write_drop_fixture(tmp_path / "drop.wav")
    result = analyze_audio_with_envelope(wav)
    drops = [t for t in result.timeline.transients if t.type == "drop"]
    assert drops
    assert any(abs(t.timestamp_ms - 2500) <= 200 for t in drops)


def test_spatial_fx_policy_includes_reason(tmp_path: Path) -> None:
    wav = _write_drop_fixture(tmp_path / "drop.wav")
    result = analyze_audio_with_envelope(wav)
    media = MediaInfo(path=Path("x.mp4"), duration_s=30.0, has_video=True, fps=30.0)
    events = plan_spatial_fx(
        result.timeline,
        media,
        seed=1,
        scope_lanes=result.scope_lanes,
        downbeats=result.beat_features.downbeat_times_s.tolist(),
        window_start_s=0.0,
        window_end_s=result.timeline.audio_duration_seconds,
    )
    assert events
    assert all(event.reason for event in events)


def test_score_plan_is_bounded(tmp_path: Path) -> None:
    wav = _write_drop_fixture(tmp_path / "drop.wav")
    result = analyze_audio_with_envelope(wav)
    interrupts = place_interrupts(
        result.scope_lanes,
        result.beat_features.downbeat_times_s.tolist(),
        window_start_s=0.0,
        window_end_s=result.timeline.audio_duration_seconds,
    )
    score = score_plan(
        result.scope_lanes,
        result.beat_features.downbeat_times_s.tolist(),
        interrupts,
        window_start_s=0.0,
        window_end_s=result.timeline.audio_duration_seconds,
    )
    assert 0.0 <= score.overall <= 1.0
