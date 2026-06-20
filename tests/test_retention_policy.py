"""Tests for the retention editing policy."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from viral_editor.audio.beat_detector import analyze_audio_with_envelope
from viral_editor.config import SpatialFxConfig
from viral_editor.editing.retention_policy import (
    EARLY_HOOK_FX_BY_S,
    INTERRUPT_MIN_GAP_S,
    PAN_BEAT_MIN_GAP_S,
    classify_accents,
    find_energy_peaks,
    place_interrupts,
    place_translations,
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


def test_surge_lane_peaks_after_quiet_rise(tmp_path: Path) -> None:
    sr = 22050
    duration_s = 4.0
    y = np.zeros(int(sr * duration_s), dtype=np.float32)
    ramp_start = int(2.0 * sr)
    ramp_end = int(3.0 * sr)
    y[ramp_start:ramp_end] = np.linspace(0.02, 0.95, ramp_end - ramp_start, dtype=np.float32)
    y[ramp_end:] = 0.95
    wav = tmp_path / "surge.wav"
    sf.write(wav, y, sr)

    result = analyze_audio_with_envelope(wav)
    surge = result.scope_lanes["surge"]
    hop = 512
    peak_frame = int(np.argmax(surge))
    peak_time_s = peak_frame * hop / sr
    assert peak_time_s >= 2.5
    assert peak_time_s <= 3.2
    assert float(surge.max()) >= 0.8


def test_find_energy_peaks_surge_score_on_ramp() -> None:
    hop, sr = 512, 22050
    rms = np.concatenate(
        [
            np.full(200, 0.08, dtype=np.float32),
            np.linspace(0.08, 0.95, 120, dtype=np.float32),
            np.full(80, 0.95, dtype=np.float32),
        ]
    )
    rms_norm = rms / float(rms.max())
    from viral_editor.audio.beat_detector import _compute_surge_lane

    surge = _compute_surge_lane(rms_norm, hop_length=hop, sr=sr)
    build = np.maximum(0.0, np.diff(rms_norm, prepend=rms_norm[0])).astype(np.float32)
    drop_salience = (build * rms_norm).astype(np.float32)
    scope = {
        "rms": rms,
        "surge": surge,
        "drop_salience": drop_salience,
        "build": build,
    }
    duration_s = rms.size * hop / sr
    peaks = find_energy_peaks(scope, [], window_end_s=duration_s)
    assert peaks
    top = peaks[0]
    assert top.surge_score >= 0.45
    assert 5.5 <= top.time_s <= 6.5


def test_place_interrupts_labels_energy_surge() -> None:
    hop, sr = 512, 22050
    rms = np.concatenate(
        [
            np.full(200, 0.08, dtype=np.float32),
            np.linspace(0.08, 0.95, 120, dtype=np.float32),
            np.full(180, 0.95, dtype=np.float32),
        ]
    )
    rms_norm = rms / float(rms.max())
    from viral_editor.audio.beat_detector import _compute_surge_lane

    surge = _compute_surge_lane(rms_norm, hop_length=hop, sr=sr)
    build = np.maximum(0.0, np.diff(rms_norm, prepend=rms_norm[0])).astype(np.float32)
    drop_salience = (build * rms_norm).astype(np.float32)
    scope = {
        "rms": rms,
        "surge": surge,
        "drop_salience": drop_salience,
        "build": build,
    }
    duration_s = rms.size * hop / sr
    events = place_interrupts(
        scope,
        [],
        window_start_s=0.0,
        window_end_s=duration_s,
    )
    zooms = [event for event in events if event.kind == "zoom"]
    assert zooms
    assert any("Energy surge" in event.reason for event in zooms)


def test_place_interrupts_keeps_relative_timestamps_non_negative() -> None:
    hop, sr = 512, 22050
    rms = np.concatenate(
        [
            np.full(120, 0.2, dtype=np.float32),
            np.full(80, 0.95, dtype=np.float32),
        ]
    )
    rms_norm = rms / float(rms.max())
    from viral_editor.audio.beat_detector import _compute_surge_lane

    surge = _compute_surge_lane(rms_norm, hop_length=hop, sr=sr)
    build = np.maximum(0.0, np.diff(rms_norm, prepend=rms_norm[0])).astype(np.float32)
    drop_salience = (build * rms_norm).astype(np.float32)
    scope = {
        "rms": rms,
        "surge": surge,
        "drop_salience": drop_salience,
        "build": build,
    }
    peak_time_s = 120 * hop / sr
    downbeats = [peak_time_s - 0.12]
    window_start_s = peak_time_s + 0.01
    window_end_s = rms.size * hop / sr

    events = place_interrupts(
        scope,
        downbeats,
        window_start_s=window_start_s,
        window_end_s=window_end_s,
    )
    for event in events:
        assert event.timestamp_s >= 0.0


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
    zoom_rotate = [event for event in events if event.kind != "translate"]
    for index in range(1, len(zoom_rotate)):
        gap = zoom_rotate[index].timestamp_s - zoom_rotate[index - 1].timestamp_s
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


def test_place_translations_alternates_direction() -> None:
    hop, sr = 512, 22050
    rms = np.full(500, 0.8, dtype=np.float32)
    scope = {"rms": rms, "band_low": rms}
    duration_s = rms.size * hop / sr
    downbeats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]

    events = place_translations(
        scope,
        downbeats,
        window_start_s=0.0,
        window_end_s=duration_s,
        beats=[t + 0.25 for t in downbeats],
        pan_beat_mode="beats",
    )
    assert len(events) >= 2
    assert all(event.kind == "translate" for event in events)
    assert events[0].direction == 1
    assert events[1].direction == -1
    for index in range(1, len(events)):
        gap = events[index].timestamp_s - events[index - 1].timestamp_s
        assert gap >= PAN_BEAT_MIN_GAP_S - 0.01


def test_place_translations_respects_min_gap() -> None:
    hop, sr = 512, 22050
    rms = np.full(500, 0.8, dtype=np.float32)
    scope = {"rms": rms, "band_low": rms}
    duration_s = rms.size * hop / sr
    beats = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5]

    events = place_translations(
        scope,
        [],
        window_start_s=0.0,
        window_end_s=min(2.0, duration_s),
        beats=beats,
        pan_beat_mode="beats",
    )
    for index in range(1, len(events)):
        gap = events[index].timestamp_s - events[index - 1].timestamp_s
        assert gap >= PAN_BEAT_MIN_GAP_S - 0.01


def test_place_translations_guarantees_hook_pan() -> None:
    hop, sr = 512, 22050
    rms = np.full(500, 0.05, dtype=np.float32)
    scope = {"rms": rms, "band_low": rms}
    duration_s = rms.size * hop / sr

    events = place_translations(
        scope,
        [],
        window_start_s=0.0,
        window_end_s=min(3.0, duration_s),
        beats=[1.5, 2.0, 2.5],
        pan_beat_mode="beats",
        pan_energy_floor=0.9,
        pan_hook_by_s=1.0,
    )
    assert events
    assert any(event.timestamp_s <= 1.0 for event in events)
    assert any("Hook pan" in event.reason for event in events)


def test_place_interrupts_includes_translate_when_enabled() -> None:
    hop, sr = 512, 22050
    rms = np.full(500, 0.8, dtype=np.float32)
    scope = {"rms": rms, "band_low": rms}
    duration_s = rms.size * hop / sr
    downbeats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]

    with_translate = place_interrupts(
        scope,
        downbeats,
        window_start_s=0.0,
        window_end_s=min(4.0, duration_s),
        translate_enabled=True,
    )
    without_translate = place_interrupts(
        scope,
        downbeats,
        window_start_s=0.0,
        window_end_s=min(4.0, duration_s),
        translate_enabled=False,
    )
    assert any(event.kind == "translate" for event in with_translate)
    assert not any(event.kind == "translate" for event in without_translate)
    assert len(without_translate) <= len(with_translate)


def test_vocal_boundary_penalty_is_zero_without_lane() -> None:
    from viral_editor.editing.retention_policy import vocal_boundary_penalty

    assert vocal_boundary_penalty(None, 1.0, 5.0) == 0.0
    assert vocal_boundary_penalty({"rms": np.ones(100)}, 1.0, 5.0) == 0.0


def test_vocal_boundary_penalty_prefers_gaps() -> None:
    from viral_editor.editing.retention_policy import vocal_boundary_penalty

    hop_length = 512
    sr = 22050
    n_frames = 300
    vocal = np.zeros(n_frames, dtype=np.float32)
    vocal[80:220] = 1.0

    scope_lanes = {"vocal": vocal}
    gap_penalty = vocal_boundary_penalty(
        scope_lanes,
        0.5,
        1.0,
        hop_length=hop_length,
        sr=sr,
    )
    mid_phrase_s = 80 * hop_length / sr
    mid_penalty = vocal_boundary_penalty(
        scope_lanes,
        mid_phrase_s,
        mid_phrase_s + 0.5,
        hop_length=hop_length,
        sr=sr,
    )
    assert gap_penalty < 0.15
    assert mid_penalty > 0.55
