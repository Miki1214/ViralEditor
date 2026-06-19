"""Tests for the spatial FX planner."""

from __future__ import annotations

from pathlib import Path

import pytest

from viral_editor.models import AudioTimeline, MediaInfo, Transient
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


def test_rotate_direction_is_deterministic() -> None:
    from viral_editor.models import FxEvent

    event = FxEvent(timestamp_s=1.5, kind="rotate", magnitude=1.0, decay_frames=4)
    assert rotate_direction(event, seed=99) in (-1, 1)
    assert rotate_direction(event, seed=99) == rotate_direction(event, seed=99)
