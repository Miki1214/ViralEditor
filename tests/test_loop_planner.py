"""Tests for advanced loop planner."""

from __future__ import annotations

import numpy as np
import pytest

from viral_editor.audio.loop_planner import suggest_music_blocks_advanced
from viral_editor.models import AudioTimeline, MusicSection, Transient
from tests.test_structure import _synthetic_abab_features


def _timeline(duration_s: float, *, bpm: float = 120.0, transients: list[Transient] | None = None) -> AudioTimeline:
    return AudioTimeline(
        global_bpm=bpm,
        audio_duration_seconds=duration_s,
        sample_rate=22050,
        transients=transients or [],
    )


def test_downbeat_aligned_starts() -> None:
    features = _synthetic_abab_features(n_beats=120, bpm=120.0)
    timeline = _timeline(60.0, bpm=120.0)
    sections = [
        MusicSection(
            id="section_a",
            start_s=0.0,
            end_s=30.0,
            start_beat=0,
            end_beat=60,
            label="Hook 1",
            repetition_count=2,
            energy=0.7,
            is_repeated=True,
        )
    ]
    plan = suggest_music_blocks_advanced(
        timeline,
        features,
        sections,
        target_duration_s=15.0,
    )
    assert plan.blocks
    downbeats = set(round(float(t), 3) for t in features.downbeat_times_s)
    for block in plan.blocks:
        assert round(block.start_s, 3) in downbeats or block.start_s == pytest.approx(0.0, abs=0.01)


def test_whole_phrase_durations() -> None:
    features = _synthetic_abab_features(n_beats=120, bpm=120.0)
    timeline = _timeline(60.0, bpm=120.0)
    plan = suggest_music_blocks_advanced(
        timeline,
        features,
        [],
        target_duration_s=15.0,
    )
    beat = 60.0 / 120.0
    for block in plan.blocks:
        if block.phrase_bars <= 0:
            continue
        phrase_beats = block.phrase_bars * 4
        duration_beats = (block.end_s - block.start_s) / beat
        assert abs(duration_beats / phrase_beats - round(duration_beats / phrase_beats)) < 0.15


def test_periodic_features_high_loop_quality() -> None:
    n_beats = 96
    features = _synthetic_abab_features(n_beats=n_beats, bpm=120.0)
    pattern_chroma = features.chroma_sync[:, 0].copy()
    pattern_mfcc = features.mfcc_sync[:, 0].copy()
    pattern_rms = features.rms_sync[:, 0].copy()
    pattern_tonnetz = features.tonnetz_sync[:, 0].copy()
    for beat in range(n_beats):
        features.chroma_sync[:, beat] = pattern_chroma
        features.mfcc_sync[:, beat] = pattern_mfcc
        features.rms_sync[:, beat] = pattern_rms
        features.tonnetz_sync[:, beat] = pattern_tonnetz

    timeline = _timeline(48.0, bpm=120.0)
    plan = suggest_music_blocks_advanced(timeline, features, [], target_duration_s=15.0)
    assert plan.blocks
    top = max(plan.blocks, key=lambda block: block.loop_quality)
    assert top.loop_quality >= 0.75


def test_no_candidates_falls_back_to_full_track() -> None:
    features = _synthetic_abab_features(n_beats=8, bpm=120.0)
    timeline = _timeline(3.0, bpm=120.0)
    plan = suggest_music_blocks_advanced(timeline, features, [], target_duration_s=15.0)
    assert len(plan.blocks) == 1
    assert plan.blocks[0].id == "block_full"
    assert plan.use_full_track is True
    assert plan.blocks[0].end_s == pytest.approx(3.0)


def test_short_track_returns_full_block_with_preview() -> None:
    features = _synthetic_abab_features(n_beats=32, bpm=120.0)
    timeline = _timeline(12.0, bpm=120.0)
    plan = suggest_music_blocks_advanced(timeline, features, [], target_duration_s=15.0)
    assert plan.use_full_track is True
    assert plan.blocks[0].id == "block_full"
    assert plan.blocks[0].start_s == 0.0
    assert plan.blocks[0].end_s == pytest.approx(12.0)


def test_advanced_planner_is_deterministic() -> None:
    features = _synthetic_abab_features(n_beats=80)
    timeline = _timeline(40.0, transients=[
        Transient(timestamp_ms=5000, type="drop", amplitude_normalized=0.9),
    ])
    first = suggest_music_blocks_advanced(timeline, features, [], target_duration_s=15.0)
    second = suggest_music_blocks_advanced(timeline, features, [], target_duration_s=15.0)
    assert first.model_dump() == second.model_dump()
