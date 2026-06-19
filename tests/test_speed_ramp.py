"""Tests for the dynamic speed-ramp planner."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from viral_editor.config import SpeedRampConfig
from viral_editor.models import AudioTimeline, ClipInput, MediaInfo, MusicSection, SpeedRampPlan, Transient
from viral_editor.video.clip_reel import build_reel
from viral_editor.video.speed_presets import SpeedPreset
from viral_editor.video.speed_ramp import (
    _plan_with_preset,
    plan_speed_options,
    plan_speed_segments,
    trim_envelope_to_window,
)


def _timeline(
    duration_s: float,
    *,
    bpm: float = 120.0,
    transients: list[Transient] | None = None,
) -> AudioTimeline:
    return AudioTimeline(
        global_bpm=bpm,
        audio_duration_seconds=duration_s,
        sample_rate=22050,
        transients=transients or [],
    )


def _video(duration_s: float, *, fps: float = 30.0) -> MediaInfo:
    return MediaInfo(
        path=Path("assets/timelapse.mp4"),
        duration_s=duration_s,
        has_video=True,
        fps=fps,
    )


def _flat_envelope(frames: int, value: float = 0.5) -> np.ndarray:
    return np.full(frames, value, dtype=float)


def _assert_tiles_output(plan: SpeedRampPlan, *, tolerance: float = 1e-3) -> None:
    assert plan.segments
    assert plan.segments[0].out_start_s == pytest.approx(0.0, abs=tolerance)
    assert plan.segments[-1].out_end_s == pytest.approx(plan.output_duration_s, abs=tolerance)
    for left, right in zip(plan.segments, plan.segments[1:], strict=False):
        assert left.out_end_s == pytest.approx(right.out_start_s, abs=tolerance)


def test_segments_tile_output_duration() -> None:
    duration_s = 10.0
    hop = 512
    sr = 22050
    frames = int(duration_s * sr / hop)
    envelope = _flat_envelope(frames, 0.6)
    plan = plan_speed_segments(
        _timeline(duration_s),
        envelope,
        _video(120.0),
        output_duration_s=duration_s,
        config=SpeedRampConfig(alpha=10.0, s_min=1.0, s_max=20.0),
        hop_length=hop,
        sr=sr,
        output_fps=60.0,
    )
    _assert_tiles_output(plan)


def test_monotonic_source_under_scale_policy() -> None:
    plan = plan_speed_segments(
        _timeline(8.0),
        _flat_envelope(400, 0.4),
        _video(60.0, fps=30.0),
        output_duration_s=8.0,
        config=SpeedRampConfig(alpha=5.0, budget_policy="scale"),
        output_fps=60.0,
    )
    for seg in plan.segments:
        assert seg.src_end_s >= seg.src_start_s
    for left, right in zip(plan.segments, plan.segments[1:], strict=False):
        assert left.src_end_s <= right.src_start_s + 1e-3


def test_scale_policy_consumes_full_source() -> None:
    src_duration = 45.0
    plan = plan_speed_segments(
        _timeline(15.0),
        _flat_envelope(600, 0.7),
        _video(src_duration, fps=30.0),
        output_duration_s=15.0,
        config=SpeedRampConfig(alpha=8.0, s_min=1.0, s_max=25.0, budget_policy="scale"),
        output_fps=60.0,
    )
    consumed = plan.segments[-1].src_end_s
    assert consumed == pytest.approx(src_duration, rel=0.02)


def test_drop_transient_yields_slow_segment() -> None:
    drop_ms = 2000
    timeline = _timeline(
        6.0,
        transients=[Transient(timestamp_ms=drop_ms, amplitude_normalized=0.95, type="drop")],
    )
    hop = 512
    sr = 22050
    frames = int(6.0 * sr / hop)
    envelope = _flat_envelope(frames, 0.9)
    config = SpeedRampConfig(
        alpha=20.0,
        s_min=1.0,
        s_max=30.0,
        drop_window_ms=400,
        min_segment_ms=50,
        budget_policy="trim",
    )
    plan = plan_speed_segments(
        timeline,
        envelope,
        _video(90.0),
        output_duration_s=6.0,
        config=config,
        hop_length=hop,
        sr=sr,
    )
    drop_s = drop_ms / 1000.0
    slow = [
        seg
        for seg in plan.segments
        if seg.out_start_s <= drop_s < seg.out_end_s or seg.speed_factor == config.s_min
    ]
    assert slow
    assert any(seg.speed_factor == pytest.approx(config.s_min) for seg in plan.segments)


def test_alpha_zero_runs_at_s_max() -> None:
    preset = SpeedPreset(
        style="steady_flow",
        label="Constant",
        description="Test preset",
        s_min=12.0,
        s_max=12.0,
        alpha=0.0,
        drop_window_ms=300,
        bass_accent=0.0,
        density_gain=0.0,
        section_bias=0.0,
        snap_mode="grid",
        opening_slow_s=0.0,
        budget_policy="trim",
        min_segment_ms=100,
        speed_quantum=0.5,
        grid_step_ms=None,
    )
    plan = _plan_with_preset(
        _timeline(5.0),
        _flat_envelope(300, 0.8),
        _video(60.0),
        output_duration_s=5.0,
        preset=preset,
    )
    assert plan.segments
    assert all(seg.speed_factor == pytest.approx(12.0) for seg in plan.segments)


def test_loop_policy_wraps_source_cursor() -> None:
    preset = SpeedPreset(
        style="steady_flow",
        label="Loop",
        description="Test preset",
        s_min=2.0,
        s_max=2.0,
        alpha=0.0,
        drop_window_ms=300,
        bass_accent=0.0,
        density_gain=0.0,
        section_bias=0.0,
        snap_mode="grid",
        opening_slow_s=0.0,
        budget_policy="loop",
        min_segment_ms=100,
        speed_quantum=0.5,
        grid_step_ms=None,
    )
    plan = _plan_with_preset(
        _timeline(6.0),
        _flat_envelope(300, 0.5),
        _video(4.0),
        output_duration_s=6.0,
        preset=preset,
    )
    assert plan.segments
    assert any(seg.src_start_s < 4.0 for seg in plan.segments)


def test_trim_envelope_matches_timeline_window() -> None:
    hop = 512
    sr = 22050
    envelope = np.arange(1000, dtype=float)
    trimmed = trim_envelope_to_window(envelope, start_s=2.0, end_s=4.0, hop_length=hop, sr=sr)
    expected_start = int(round(2.0 * sr / hop))
    expected_end = int(round(4.0 * sr / hop))
    assert trimmed.shape[0] == expected_end - expected_start


def test_short_source_caps_output_without_flattening_speeds() -> None:
    timeline = _timeline(
        13.5,
        transients=[Transient(timestamp_ms=2000, amplitude_normalized=0.95, type="drop")],
    )
    envelope = np.linspace(0.2, 1.0, 600)
    plan = plan_speed_segments(
        timeline,
        envelope,
        _video(7.04),
        output_duration_s=13.5,
        config=SpeedRampConfig(style="drop_sync", alpha=22.0),
    )
    assert plan.output_duration_s == pytest.approx(7.04, rel=0.01)
    assert plan.requested_output_duration_s == pytest.approx(13.5, rel=0.01)
    speeds = {seg.speed_factor for seg in plan.segments}
    assert len(speeds) > 1
    assert plan.max_speed > plan.min_speed


def test_cap_output_duration_to_source() -> None:
    from viral_editor.video.speed_ramp import cap_output_duration_to_source

    assert cap_output_duration_to_source(13.5, 7.0, s_min=1.0) == pytest.approx(7.0)
    assert cap_output_duration_to_source(5.0, 7.0, s_min=1.0) == pytest.approx(5.0)
    assert cap_output_duration_to_source(13.5, 7.0, s_min=1.0, budget_policy="loop") == pytest.approx(
        13.5
    )


def test_plan_is_deterministic() -> None:
    timeline = _timeline(10.0, transients=[
        Transient(timestamp_ms=3000, amplitude_normalized=0.9, type="drop"),
    ])
    envelope = _flat_envelope(500, 0.55)
    kwargs = dict(
        video=_video(80.0),
        output_duration_s=10.0,
        config=SpeedRampConfig(alpha=6.0),
    )
    first = plan_speed_segments(timeline, envelope, **kwargs)
    second = plan_speed_segments(timeline, envelope, **kwargs)
    assert first.model_dump() == second.model_dump()


def test_speed_ramp_plan_round_trip_artifact(temp_artifacts_dir: Path) -> None:
    from viral_editor.models import read_artifact, write_artifact

    plan = plan_speed_segments(
        _timeline(4.0),
        _flat_envelope(200, 0.3),
        _video(20.0),
        output_duration_s=4.0,
        config=SpeedRampConfig(alpha=3.0),
    )
    path = write_artifact(plan, "speed_segments", temp_artifacts_dir)
    restored = read_artifact(SpeedRampPlan, path)
    assert restored == plan


def test_plan_speed_segments_with_reel_localizes_source_ids() -> None:
    clips = [
        ClipInput(id="a", path=Path("a.mp4"), order=0),
        ClipInput(id="b", path=Path("b.mp4"), order=1),
    ]
    media = {
        "a": MediaInfo(path=Path("a.mp4"), duration_s=10.0, has_video=True, fps=30.0),
        "b": MediaInfo(path=Path("b.mp4"), duration_s=8.0, has_video=True, fps=30.0),
    }
    reel = build_reel(
        clips,
        media,
        body_output_duration_s=12.0,
        speed_config=SpeedRampConfig(),
    )
    plan = plan_speed_segments(
        _timeline(12.0),
        _flat_envelope(300, 0.4),
        _video(18.0),
        output_duration_s=12.0,
        config=SpeedRampConfig(style="steady_flow"),
        reel=reel,
    )
    assert plan.src_duration_s == pytest.approx(reel.reel_duration_s)
    source_ids = {segment.source_id for segment in plan.segments}
    assert source_ids <= {"a", "b", None}


def test_plan_speed_options_is_deterministic() -> None:
    timeline = _timeline(8.0, transients=[
        Transient(timestamp_ms=1500, amplitude_normalized=0.8, type="bass"),
        Transient(timestamp_ms=4000, amplitude_normalized=0.95, type="drop"),
    ])
    envelope = _flat_envelope(400, 0.6)
    kwargs = dict(
        video=_video(70.0),
        output_duration_s=8.0,
        base_config=SpeedRampConfig(style="drop_sync"),
    )
    first = plan_speed_options(timeline, envelope, **kwargs)
    second = plan_speed_options(timeline, envelope, **kwargs)
    assert first.model_dump() == second.model_dump()
    assert len(first.options) == 4


def test_repeated_section_yields_slower_target() -> None:
    sections = [
        MusicSection(
            id="hook",
            start_s=0.0,
            end_s=4.0,
            start_beat=0,
            end_beat=8,
            label="Hook",
            repetition_count=2,
            energy=0.9,
            drop_count=0,
            is_repeated=True,
        ),
        MusicSection(
            id="verse",
            start_s=4.0,
            end_s=8.0,
            start_beat=8,
            end_beat=16,
            label="Verse",
            repetition_count=1,
            energy=0.4,
            drop_count=0,
            is_repeated=False,
        ),
    ]
    preset = SpeedPreset(
        style="slow_burn_hook",
        label="Slow burn",
        description="Test",
        s_min=1.0,
        s_max=20.0,
        alpha=12.0,
        drop_window_ms=300,
        bass_accent=0.0,
        density_gain=0.0,
        section_bias=0.5,
        snap_mode="grid",
        opening_slow_s=0.0,
        budget_policy="trim",
        min_segment_ms=200,
        speed_quantum=0.5,
        grid_step_ms=500,
    )
    plan = _plan_with_preset(
        _timeline(8.0),
        _flat_envelope(400, 0.7),
        _video(80.0),
        output_duration_s=8.0,
        preset=preset,
        sections=sections,
    )
    hook_speeds = [
        seg.speed_factor
        for seg in plan.segments
        if seg.out_start_s < 4.0
    ]
    verse_speeds = [
        seg.speed_factor
        for seg in plan.segments
        if seg.out_start_s >= 4.0
    ]
    assert hook_speeds
    assert verse_speeds
    assert sum(hook_speeds) / len(hook_speeds) < sum(verse_speeds) / len(verse_speeds)


def test_bass_transient_produces_slow_accent() -> None:
    timeline = _timeline(
        6.0,
        transients=[Transient(timestamp_ms=2000, amplitude_normalized=0.8, type="bass")],
    )
    preset = SpeedPreset(
        style="high_energy",
        label="High energy",
        description="Test",
        s_min=1.0,
        s_max=24.0,
        alpha=8.0,
        drop_window_ms=300,
        bass_accent=0.8,
        density_gain=0.0,
        section_bias=0.0,
        snap_mode="grid",
        opening_slow_s=0.0,
        budget_policy="trim",
        min_segment_ms=80,
        speed_quantum=0.5,
        grid_step_ms=250,
    )
    plan = _plan_with_preset(
        timeline,
        _flat_envelope(300, 0.5),
        _video(90.0),
        output_duration_s=6.0,
        preset=preset,
    )
    bass_points = [point for point in plan.speed_curve if point.is_bass_accent]
    assert bass_points
