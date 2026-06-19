"""Tests for music block suggestion."""

from __future__ import annotations

import numpy as np
import pytest

from viral_editor.audio.block_planner import (
    _loop_repeat_score,
    suggest_music_blocks,
    trim_timeline_to_window,
)
from viral_editor.models import AudioTimeline, Transient


def _timeline(duration_s: float, *, bpm: float = 120.0, transients: list[Transient] | None = None) -> AudioTimeline:
    return AudioTimeline(
        global_bpm=bpm,
        audio_duration_seconds=duration_s,
        sample_rate=22050,
        transients=transients or [],
    )


def test_short_track_returns_full_block() -> None:
    timeline = _timeline(15.0, transients=[
        Transient(timestamp_ms=2000, type="drop", amplitude_normalized=0.9),
    ])
    envelope = np.ones(100)
    plan = suggest_music_blocks(timeline, envelope, target_duration_s=30.0)
    assert plan.use_full_track is True
    assert len(plan.blocks) == 1
    assert plan.blocks[0].id == "block_full"
    assert plan.selected_block_id == "block_full"
    assert plan.blocks[0].duration_s == pytest.approx(15.0)


def test_top_block_overlaps_energy_peak() -> None:
    duration_s = 60.0
    sr = 22050
    hop = 512
    frames = int(duration_s * sr / hop)
    envelope = np.zeros(frames)
    peak_center_s = 25.0
    peak_frame = int(peak_center_s * sr / hop)
    envelope[peak_frame - 5 : peak_frame + 5] = 1.0

    drop_ms = int(peak_center_s * 1000)
    transients = [
        Transient(timestamp_ms=drop_ms, type="drop", amplitude_normalized=1.0),
        Transient(timestamp_ms=drop_ms + 500, type="bass", amplitude_normalized=0.8),
    ]
    timeline = _timeline(duration_s, bpm=120.0, transients=transients)
    plan = suggest_music_blocks(timeline, envelope, target_duration_s=15.0)

    assert len(plan.blocks) >= 1
    top = max(plan.blocks, key=lambda block: block.score)
    assert top.start_s <= peak_center_s <= top.end_s


def test_windows_drift_from_target_for_loop_alignment() -> None:
    timeline = _timeline(90.0, bpm=120.0)
    envelope = np.linspace(0.1, 1.0, 2000)
    target = 20.0
    plan = suggest_music_blocks(timeline, envelope, target_duration_s=target)
    bar = 2.0  # 120 BPM, 4/4
    for block in plan.blocks:
        duration = block.end_s - block.start_s
        assert abs(duration - target) <= target * 0.28 + 0.15
        beat = 60.0 / 120.0
        beats = duration / beat
        assert abs(beats - round(beats)) < 0.08


def test_repeat_score_prefers_matching_head_and_tail() -> None:
    bpm = 120.0
    bar = 2.0
    duration_s = 40.0
    sr = 22050
    hop = 512
    frames = int(duration_s * sr / hop)
    t = np.arange(frames) * hop / sr
    envelope = (0.4 + 0.35 * np.sin(2 * np.pi * t / bar)).astype(float)

    start_s = 4.0
    good_end = start_s + 8 * bar
    bad_end = start_s + 8 * bar + 0.37
    timeline = _timeline(duration_s, bpm=bpm)

    good = _loop_repeat_score(
        start_s,
        good_end,
        envelope,
        None,
        bpm=bpm,
        transients=timeline.transients,
        hop_length=hop,
        sr=sr,
    )
    bad = _loop_repeat_score(
        start_s,
        bad_end,
        envelope,
        None,
        bpm=bpm,
        transients=timeline.transients,
        hop_length=hop,
        sr=sr,
    )
    assert good > bad


def test_periodic_envelope_prefers_seamless_bar_loop() -> None:
    bpm = 120.0
    bar = 2.0
    duration_s = 60.0
    sr = 22050
    hop = 512
    frames = int(duration_s * sr / hop)
    t = np.arange(frames) * hop / sr
    envelope = (0.35 + 0.25 * np.sin(2 * np.pi * t / bar)).astype(float)

    timeline = _timeline(duration_s, bpm=bpm)
    plan = suggest_music_blocks(timeline, envelope, target_duration_s=15.0, max_blocks=3)
    assert plan.blocks
    top = max(plan.blocks, key=lambda block: block.score)
    loop_duration = top.end_s - top.start_s
    assert abs(loop_duration / bar - round(loop_duration / bar)) < 0.08


def test_suggest_is_deterministic() -> None:
    timeline = _timeline(45.0, transients=[
        Transient(timestamp_ms=5000, type="drop", amplitude_normalized=0.9),
        Transient(timestamp_ms=15000, type="drop", amplitude_normalized=0.95),
    ])
    envelope = np.sin(np.linspace(0, 12, 1500)) ** 2
    first = suggest_music_blocks(timeline, envelope, target_duration_s=15.0)
    second = suggest_music_blocks(timeline, envelope, target_duration_s=15.0)
    assert first.model_dump() == second.model_dump()


def test_suggested_blocks_have_varied_labels() -> None:
    transients = [
        Transient(timestamp_ms=int(10_000), type="drop", amplitude_normalized=0.95),
        Transient(timestamp_ms=int(10_200), type="bass", amplitude_normalized=0.7),
        Transient(timestamp_ms=int(40_000), type="drop", amplitude_normalized=0.9),
        Transient(timestamp_ms=int(40_300), type="percussive", amplitude_normalized=0.6),
        Transient(timestamp_ms=int(70_000), type="drop", amplitude_normalized=0.85),
        Transient(timestamp_ms=int(100_000), type="drop", amplitude_normalized=0.92),
        Transient(timestamp_ms=int(100_500), type="drop", amplitude_normalized=0.88),
    ]
    timeline = _timeline(120.0, bpm=128.0, transients=transients)
    envelope = np.sin(np.linspace(0, 24, 3000)) ** 2
    plan = suggest_music_blocks(timeline, envelope, target_duration_s=15.0, max_blocks=5)

    assert len(plan.blocks) >= 2
    reasons = {block.reason for block in plan.blocks}
    assert len(reasons) >= 2
    assert not all(block.reason.startswith("Starts near a drop") for block in plan.blocks)


def test_trim_timeline_offsets_transients() -> None:
    timeline = _timeline(30.0, transients=[
        Transient(timestamp_ms=5000, type="bass", amplitude_normalized=0.5),
        Transient(timestamp_ms=15000, type="drop", amplitude_normalized=0.9),
    ])
    trimmed = trim_timeline_to_window(timeline, start_s=10.0, end_s=20.0)
    assert trimmed.audio_duration_seconds == pytest.approx(10.0)
    assert len(trimmed.transients) == 1
    assert trimmed.transients[0].timestamp_ms == 5000
