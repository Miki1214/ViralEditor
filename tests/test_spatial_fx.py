"""Tests for the spatial FX planner."""

from __future__ import annotations

from pathlib import Path

import pytest

from viral_editor.config import SpatialFxConfig
from viral_editor.models import AudioTimeline, FxEvent, MediaInfo, Transient
from viral_editor.video.spatial_fx import (
    ROTATE_MAX_DEG,
    ZOOM_MAX,
    ZOOM_MIN,
    plan_spatial_fx,
    rotate_direction,
)


def _video() -> MediaInfo:
    return MediaInfo(
        path=Path("assets/timelapse.mp4"),
        duration_s=30.0,
        has_video=True,
        fps=30.0,
    )


def _timeline(transients: list[Transient]) -> AudioTimeline:
    return AudioTimeline(
        global_bpm=128.0,
        audio_duration_seconds=30.0,
        sample_rate=44100,
        transients=transients,
    )


def test_drop_produces_zoom_event() -> None:
    events = plan_spatial_fx(
        _timeline([
            Transient(timestamp_ms=4720, amplitude_normalized=0.99, type="drop"),
        ]),
        _video(),
        seed=42,
    )
    assert len(events) == 1
    assert events[0].kind == "zoom"
    assert events[0].timestamp_s == pytest.approx(4.72)
    assert ZOOM_MIN <= events[0].magnitude <= ZOOM_MAX


def test_bass_produces_rotate_event() -> None:
    events = plan_spatial_fx(
        _timeline([
            Transient(timestamp_ms=1500, amplitude_normalized=0.8, type="bass"),
        ]),
        _video(),
        seed=42,
    )
    assert len(events) == 1
    assert events[0].kind == "rotate"
    assert 0.0 < events[0].magnitude <= ROTATE_MAX_DEG


def test_percussive_transient_produces_no_event() -> None:
    events = plan_spatial_fx(
        _timeline([
            Transient(timestamp_ms=900, amplitude_normalized=0.7, type="percussive"),
        ]),
        _video(),
        seed=42,
    )
    assert events == []


def test_magnitude_and_decay_scale_with_amplitude() -> None:
    low = plan_spatial_fx(
        _timeline([
            Transient(timestamp_ms=1000, amplitude_normalized=0.2, type="drop"),
        ]),
        _video(),
        seed=1,
    )[0]
    high = plan_spatial_fx(
        _timeline([
            Transient(timestamp_ms=1000, amplitude_normalized=1.0, type="drop"),
        ]),
        _video(),
        seed=1,
    )[0]
    assert high.magnitude > low.magnitude
    assert high.decay_frames >= low.decay_frames


def test_plan_is_deterministic_with_fixed_seed() -> None:
    timeline = _timeline([
        Transient(timestamp_ms=1000, amplitude_normalized=0.6, type="bass"),
        Transient(timestamp_ms=2500, amplitude_normalized=0.95, type="drop"),
    ])
    first = plan_spatial_fx(timeline, _video(), seed=7)
    second = plan_spatial_fx(timeline, _video(), seed=7)
    assert [event.model_dump() for event in first] == [event.model_dump() for event in second]


def test_merge_keeps_stronger_event_in_window() -> None:
    events = plan_spatial_fx(
        _timeline([
            Transient(timestamp_ms=1000, amplitude_normalized=0.4, type="drop"),
            Transient(timestamp_ms=1020, amplitude_normalized=0.95, type="drop"),
        ]),
        _video(),
        seed=3,
        merge_window_s=0.05,
    )
    assert len(events) == 1
    assert events[0].magnitude > 1.06


def test_cap_limits_dense_events() -> None:
    transients = [
        Transient(timestamp_ms=1000 + index * 10, amplitude_normalized=0.9, type="drop")
        for index in range(20)
    ]
    events = plan_spatial_fx(
        _timeline(transients),
        _video(),
        seed=5,
        max_events_per_second=4.0,
        merge_window_s=0.0,
    )
    bucket_count = sum(1 for event in events if 1.0 <= event.timestamp_s < 2.0)
    assert bucket_count <= 4


def test_policy_includes_translate_events() -> None:
    import numpy as np

    hop, sr = 512, 22050
    rms = np.full(500, 0.8, dtype=np.float32)
    scope = {"rms": rms, "band_low": rms}
    duration_s = rms.size * hop / sr
    downbeats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    timeline = AudioTimeline(
        global_bpm=128.0,
        audio_duration_seconds=duration_s,
        sample_rate=sr,
        transients=[],
    )
    events = plan_spatial_fx(
        timeline,
        _video(),
        seed=1,
        scope_lanes=scope,
        downbeats=downbeats,
        beats=[t + 0.25 for t in downbeats],
        window_start_s=0.0,
        window_end_s=min(4.0, duration_s),
        max_events_per_second=8.0,
        spatial_fx=SpatialFxConfig(translate_enabled=True, pan_beat_mode="beats"),
    )
    translate_events = [event for event in events if event.kind == "translate"]
    assert translate_events
    assert translate_events[0].direction in (-1, 1)


def test_merge_keeps_opposite_direction_translations() -> None:
    from viral_editor.video.spatial_fx import _merge_nearby

    left = FxEvent(
        timestamp_s=1.0,
        kind="translate",
        magnitude=0.8,
        decay_frames=4,
        direction=-1,
    )
    right = FxEvent(
        timestamp_s=1.02,
        kind="translate",
        magnitude=0.7,
        decay_frames=4,
        direction=1,
    )
    merged = _merge_nearby([left, right], merge_window_s=0.05)
    assert len(merged) == 2


def test_rotate_direction_is_deterministic() -> None:
    from viral_editor.models import FxEvent

    event = FxEvent(timestamp_s=1.5, kind="rotate", magnitude=1.0, decay_frames=4)
    assert rotate_direction(event, seed=99) in (-1, 1)
    assert rotate_direction(event, seed=99) == rotate_direction(event, seed=99)
