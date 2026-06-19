"""Tests for advanced loop planner."""

from __future__ import annotations

import numpy as np
import pytest

from viral_editor.audio.features import BeatSyncFeatures
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


def test_list_target_loop_qualities(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    features = _synthetic_abab_features(n_beats=120, bpm=120.0)
    timeline = _timeline(60.0, bpm=120.0)

    def fake_enumerate(
        _timeline: AudioTimeline,
        _features: BeatSyncFeatures,
        _sections: list[MusicSection],
        *,
        target_duration_s: float,
    ) -> list:
        from viral_editor.audio.loop_planner import _Candidate

        if target_duration_s in (5, 10, 15):
            return [
                _Candidate(
                    start_s=0.0,
                    end_s=target_duration_s,
                    start_beat=0,
                    end_beat=20,
                    phrase_bars=4,
                    retention=0.5,
                    loop_quality={5: 0.7, 10: 0.75, 15: 0.8}[target_duration_s],
                    section_label=None,
                    is_repeated_section=False,
                    drop_count=0,
                    transient_count=1,
                    label="Phrase loop",
                    reason="Test window",
                )
            ]
        if target_duration_s == 20:
            return [
                _Candidate(
                    start_s=0.0,
                    end_s=20.0,
                    start_beat=0,
                    end_beat=40,
                    phrase_bars=8,
                    retention=0.8,
                    loop_quality=0.99,
                    section_label=None,
                    is_repeated_section=False,
                    drop_count=1,
                    transient_count=2,
                    label="Phrase loop",
                    reason="Test window",
                )
            ]
        return []

    monkeypatch.setattr(
        "viral_editor.audio.loop_planner._enumerate_phrase_candidates",
        fake_enumerate,
    )
    from viral_editor.audio.loop_planner import list_target_loop_qualities

    qualities = list_target_loop_qualities(timeline, features, [])
    by_duration = {int(q.target_duration_s): q.loop_quality_pct for q in qualities}
    assert by_duration[5] == 70
    assert by_duration[10] == 75
    assert by_duration[15] == 80
    assert by_duration[20] == 99


def test_tied_best_loop_targets_share_top_score(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    features = _synthetic_abab_features(n_beats=120, bpm=120.0)
    timeline = _timeline(60.0, bpm=120.0)

    def fake_enumerate(
        _timeline: AudioTimeline,
        _features: BeatSyncFeatures,
        _sections: list[MusicSection],
        *,
        target_duration_s: float,
    ) -> list:
        from viral_editor.audio.loop_planner import _Candidate

        if target_duration_s in (15, 20, 25):
            return [
                _Candidate(
                    start_s=0.0,
                    end_s=target_duration_s,
                    start_beat=0,
                    end_beat=40,
                    phrase_bars=8,
                    retention=0.8,
                    loop_quality=0.99,
                    section_label=None,
                    is_repeated_section=False,
                    drop_count=1,
                    transient_count=2,
                    label="Phrase loop",
                    reason="Test window",
                )
            ]
        if target_duration_s == 10:
            return [
                _Candidate(
                    start_s=0.0,
                    end_s=10.0,
                    start_beat=0,
                    end_beat=20,
                    phrase_bars=4,
                    retention=0.5,
                    loop_quality=0.75,
                    section_label=None,
                    is_repeated_section=False,
                    drop_count=0,
                    transient_count=1,
                    label="Phrase loop",
                    reason="Test window",
                )
            ]
        return []

    monkeypatch.setattr(
        "viral_editor.audio.loop_planner._enumerate_phrase_candidates",
        fake_enumerate,
    )
    from viral_editor.audio.waveform import build_waveform_payload
    import numpy as np
    from viral_editor.models import MusicBlockPlan

    payload = build_waveform_payload(
        timeline,
        np.linspace(0.1, 1.0, 500),
        MusicBlockPlan(target_duration_s=10.0, track_duration_s=60.0, blocks=[]),
        features=features,
    )
    assert sorted(payload.best_loop_target_durations_s) == [15.0, 20.0, 25.0]


def test_list_matchable_target_durations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    features = _synthetic_abab_features(n_beats=120, bpm=120.0)
    timeline = _timeline(60.0, bpm=120.0)

    def fake_enumerate(
        _timeline: AudioTimeline,
        _features: BeatSyncFeatures,
        _sections: list[MusicSection],
        *,
        target_duration_s: float,
    ) -> list:
        from viral_editor.audio.loop_planner import _Candidate

        if target_duration_s in (5, 10, 15):
            return []
        if target_duration_s == 20:
            return [
                _Candidate(
                    start_s=0.0,
                    end_s=20.0,
                    start_beat=0,
                    end_beat=40,
                    phrase_bars=8,
                    retention=0.8,
                    loop_quality=0.8,
                    section_label=None,
                    is_repeated_section=False,
                    drop_count=1,
                    transient_count=2,
                    label="Phrase loop",
                    reason="Test window",
                )
            ]
        return []

    monkeypatch.setattr(
        "viral_editor.audio.loop_planner._enumerate_phrase_candidates",
        fake_enumerate,
    )
    from viral_editor.audio.loop_planner import list_matchable_target_durations

    matchable = list_matchable_target_durations(timeline, features, [])
    assert matchable == [20.0]


def test_no_match_suggests_nearest_duration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    features = _synthetic_abab_features(n_beats=120, bpm=120.0)
    timeline = _timeline(60.0, bpm=120.0)

    def fake_enumerate(
        _timeline: AudioTimeline,
        _features: BeatSyncFeatures,
        _sections: list[MusicSection],
        *,
        target_duration_s: float,
    ) -> list:
        from viral_editor.audio.loop_planner import _Candidate

        if target_duration_s in (5, 10, 15):
            return []
        if target_duration_s == 20:
            return [
                _Candidate(
                    start_s=0.0,
                    end_s=20.0,
                    start_beat=0,
                    end_beat=40,
                    phrase_bars=8,
                    retention=0.8,
                    loop_quality=0.8,
                    section_label=None,
                    is_repeated_section=False,
                    drop_count=1,
                    transient_count=2,
                    label="Phrase loop",
                    reason="Test window",
                )
            ]
        return []

    monkeypatch.setattr(
        "viral_editor.audio.loop_planner._enumerate_phrase_candidates",
        fake_enumerate,
    )
    plan = suggest_music_blocks_advanced(timeline, features, [], target_duration_s=10.0)
    assert plan.use_full_track is True
    assert plan.target_match_failed is True
    assert plan.suggested_target_duration_s == 20.0


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
