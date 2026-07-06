"""Tests for storyboard planner."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from viral_editor.audio.features import BeatFeaturesMeta, BeatSyncFeatures
from viral_editor.audio.storyboard import (
    _compute_boundaries,
    _recommended_slot_count,
    _salient_boundaries,
    _soft_count_range,
    apply_hook_inversion_layout,
    hook_payoff_downbeats_s,
    plan_storyboard,
    relayout_beat_aligned_timeline,
    snap_hook_payoff_s,
    storyboard_filled_enough,
    storyboard_slots_complete,
    storyboard_to_segments,
)
from viral_editor.models import MediaInfo, MusicBlock, MusicBlockPlan, Transient

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "audio"


def _block(duration: float = 30.0) -> MusicBlock:
    return MusicBlock(
        id="block_a",
        start_s=10.0,
        end_s=10.0 + duration,
        duration_s=duration,
        score=0.9,
        drop_count=2,
        transient_count=5,
        label="Chorus",
        reason="test",
        loop_quality=0.8,
        phrase_bars=8,
    )


def _features(downbeats: list[float]) -> BeatSyncFeatures:
    beats = np.array(downbeats, dtype=np.float64)
    n = len(beats)
    return BeatSyncFeatures(
        beat_times_s=beats,
        downbeat_times_s=beats,
        chroma_sync=np.zeros((12, n)),
        mfcc_sync=np.zeros((20, n)),
        rms_sync=np.zeros((1, n)),
        contrast_sync=np.zeros((7, n)),
        tonnetz_sync=np.zeros((6, n)),
        meta=BeatFeaturesMeta(
            engine="test",
            global_bpm=120.0,
            key="C",
            n_beats=n,
            n_downbeats=n,
            hop_length=512,
            sample_rate=22050,
        ),
    )


def test_plan_storyboard_creates_hook_and_slots() -> None:
    block = _block(24.0)
    features = _features([10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 34.0])
    storyboard = plan_storyboard(block, features=features, transients=[])
    assert len(storyboard.slots) >= 2
    assert storyboard.slots[0].role == "hook"
    assert storyboard.loop_to_hook is True
    assert storyboard.total_duration_s == pytest.approx(24.0)


def _assert_slots_tile_timeline(slots, total_duration_s: float) -> None:
    """Slots partition the block: no overlap, no zero width, full coverage."""
    ordered = sorted(slots, key=lambda slot: slot.order)
    assert ordered, "expected at least one slot"
    assert ordered[0].out_start_s == pytest.approx(0.0)
    assert ordered[-1].out_end_s == pytest.approx(total_duration_s, abs=1e-3)
    for slot in ordered:
        span = slot.out_end_s - slot.out_start_s
        assert span > 1e-6, f"{slot.role} has zero width"
        assert slot.out_start_s >= -1e-3
        assert slot.out_end_s <= total_duration_s + 1e-3
    for left, right in zip(ordered, ordered[1:]):
        assert left.out_end_s <= right.out_start_s + 1e-3, "slots overlap on timeline"
        assert left.out_end_s == pytest.approx(right.out_start_s, abs=1e-3)


def _short_block(duration_s: float = 5.5) -> MusicBlock:
    return MusicBlock(
        id="short",
        start_s=0.0,
        end_s=duration_s,
        duration_s=duration_s,
        score=0.9,
        drop_count=1,
        transient_count=4,
        label="Full",
        reason="test",
        loop_quality=0.5,
        phrase_bars=4,
    )


@pytest.mark.parametrize(
    ("duration_s", "expected_slots"),
    [
        (4.0, 1),
        (5.5, 1),
        (6.0, 2),
        (8.0, 2),
        (12.0, 3),
        (24.0, 6),
    ],
)
def test_recommended_slot_count_scales_with_duration(
    duration_s: float,
    expected_slots: int,
) -> None:
    assert _recommended_slot_count(duration_s) == expected_slots


def test_recommended_slot_count_respects_explicit_cap() -> None:
    assert _recommended_slot_count(5.5, target_slot_count=3) == 3
    assert _recommended_slot_count(4.0, target_slot_count=5) == 2


def test_compute_boundaries_no_duplicate_endpoints() -> None:
    """Regression: sparse downbeats used to pad with repeated window_end (e.g. [0, 2, 5.5, 5.5])."""
    downbeats = [0.0, 1.0, 2.0, 3.0, 4.0, 5.0]
    bounds = _compute_boundaries(0.0, 5.5, downbeats, 3).boundaries
    assert len(bounds) == 4
    assert bounds[0] == pytest.approx(0.0)
    assert bounds[-1] == pytest.approx(5.5)
    assert len({round(value, 4) for value in bounds}) == len(bounds)
    spans = [bounds[index + 1] - bounds[index] for index in range(len(bounds) - 1)]
    assert all(span >= 1.5 - 1e-3 for span in spans)


def test_short_track_uses_single_slot_without_overlap() -> None:
    """Short fixtures (e.g. validation_drop.wav) should not force three overlapping clips."""
    block = _short_block(5.5)
    features = _features([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    transients = [
        Transient(timestamp_ms=2485, amplitude_normalized=1.0, type="drop"),
    ]
    storyboard = plan_storyboard(block, features=features, transients=transients)
    assert len(storyboard.slots) == 1
    assert storyboard.slots[0].role == "hook"

    relaid = relayout_beat_aligned_timeline(
        storyboard.slots,
        total_duration_s=storyboard.total_duration_s,
        features=features,
    )
    _assert_slots_tile_timeline(relaid, storyboard.total_duration_s)


def test_explicit_three_slots_on_short_block_stays_within_duration() -> None:
    """Even when three slots are requested, relayout must not extend past the block."""
    block = _short_block(5.5)
    features = _features([0.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    storyboard = plan_storyboard(
        block,
        features=features,
        transients=[],
        target_slot_count=3,
    )
    assert len(storyboard.slots) == 3

    relaid = relayout_beat_aligned_timeline(
        storyboard.slots,
        total_duration_s=storyboard.total_duration_s,
        features=features,
    )
    _assert_slots_tile_timeline(relaid, storyboard.total_duration_s)


def test_plan_and_relayout_never_overlap_for_varied_durations() -> None:
    for duration_s in (4.0, 5.5, 8.0, 12.0, 17.74, 24.0):
        block = _short_block(duration_s)
        downbeat_step = max(1.0, duration_s / 8.0)
        downbeats = [round(index * downbeat_step, 3) for index in range(int(duration_s / downbeat_step) + 1)]
        features = _features(downbeats)
        storyboard = plan_storyboard(block, features=features, transients=[])
        relaid = relayout_beat_aligned_timeline(
            storyboard.slots,
            total_duration_s=storyboard.total_duration_s,
            features=features,
        )
        _assert_slots_tile_timeline(relaid, storyboard.total_duration_s)


def test_validation_drop_fixture_storyboard() -> None:
    """End-to-end: validation_drop.wav should plan a single non-overlapping hook slot."""
    from viral_editor.audio.beat_detector import AudioDspConfig, analyze_audio_with_envelope
    from viral_editor.audio.waveform import build_waveform_payload

    path = FIXTURES_DIR / "validation_drop.wav"
    assert path.is_file()

    result = analyze_audio_with_envelope(
        path,
        config=AudioDspConfig(drop_percentile=0.85, min_drop_gap_ms=800),
    )
    duration = result.timeline.audio_duration_seconds
    block = _short_block(duration)
    storyboard = plan_storyboard(
        block,
        features=result.beat_features,
        transients=result.timeline.transients,
    )
    assert len(storyboard.slots) == 1
    assert storyboard.slots[0].role == "hook"

    relaid = relayout_beat_aligned_timeline(
        storyboard.slots,
        total_duration_s=storyboard.total_duration_s,
        features=result.beat_features,
    )
    _assert_slots_tile_timeline(relaid, storyboard.total_duration_s)

    block_plan = MusicBlockPlan(
        target_duration_s=10.0,
        track_duration_s=duration,
        blocks=[],
    )
    payload = build_waveform_payload(
        result.timeline,
        result.onset_envelope,
        block_plan,
        features=result.beat_features,
        scope_lanes=result.scope_lanes,
    )
    assert payload.lanes
    assert payload.chroma is not None


def test_plan_storyboard_marks_max_drop_as_punch() -> None:
    block = _block(20.0)
    features = _features([10.0, 12.0, 14.0, 16.0, 18.0, 30.0])
    transients = [
        Transient(timestamp_ms=int(11_000), amplitude_normalized=0.9, type="drop"),
        Transient(timestamp_ms=int(17_000), amplitude_normalized=0.95, type="drop"),
        Transient(timestamp_ms=int(17_500), amplitude_normalized=0.99, type="drop"),
    ]
    storyboard = plan_storyboard(block, features=features, transients=transients)
    roles = [slot.role for slot in storyboard.slots]
    assert "punch" in roles


def test_storyboard_to_segments_maps_crops() -> None:
    block = _block(12.0)
    storyboard = plan_storyboard(block, features=None, transients=[])
    hook = storyboard.slots[0].model_copy(
        update={
            "assigned_clip_id": "slot_0_clip",
            "crop_start_s": 0.0,
            "crop_end_s": 4.0,
        }
    )
    storyboard = storyboard.model_copy(update={"slots": [hook, *storyboard.slots[1:]]})
    media = {
        "slot_0_clip": MediaInfo(
            path=__file__,
            duration_s=10.0,
            has_video=True,
        )
    }
    segments, roles, slot_ids = storyboard_to_segments(storyboard, media)
    assert len(segments) == 1
    assert roles == ["hook"]
    assert slot_ids == [hook.id]
    assert segments[0].source_id == "slot_0_clip"
    assert segments[0].src_end_s - segments[0].src_start_s == pytest.approx(4.0)


def test_apply_hook_inversion_layout_splits_hook_slots() -> None:
    block = _block(12.0)
    storyboard = plan_storyboard(block, features=None, transients=[])
    hook = storyboard.slots[0].model_copy(
        update={
            "assigned_clip_id": "slot_0_clip",
            "crop_start_s": 0.0,
            "crop_end_s": 3.0,
        }
    )
    storyboard = storyboard.model_copy(update={"slots": [hook, *storyboard.slots[1:]]})
    split = apply_hook_inversion_layout(
        storyboard,
        enabled=True,
        payoff_duration_s=1.0,
    )
    roles = [slot.role for slot in sorted(split.slots, key=lambda item: item.order)]
    assert roles[0] == "hook_start"
    assert roles[-1] == "hook_end"
    hook_start = split.slots[0]
    hook_end = next(slot for slot in split.slots if slot.role == "hook_end")
    hook_budget = hook_start.target_duration_s + hook_end.target_duration_s
    positions = hook_payoff_downbeats_s(
        hook_budget,
        None,
        music_start_s=storyboard.music_start_s,
        music_end_s=storyboard.music_end_s,
    )
    assert hook_start.target_duration_s in positions
    assert hook_end.target_duration_s == pytest.approx(hook_budget - hook_start.target_duration_s)
    total_source = hook_end.crop_end_s - hook_end.crop_start_s + (
        hook_start.crop_end_s - hook_start.crop_start_s
    )
    assert total_source == pytest.approx(3.0, abs=0.01)
    payoff_src = hook_start.crop_end_s - hook_start.crop_start_s
    build_src = hook_end.crop_end_s - hook_end.crop_start_s
    assert payoff_src == pytest.approx(build_src, rel=0.05)
    assert payoff_src / hook_start.target_duration_s == pytest.approx(
        build_src / hook_end.target_duration_s,
        rel=0.02,
    )


def test_hook_split_uses_full_clip_span_when_assigned() -> None:
    block = _block(12.0)
    storyboard = plan_storyboard(block, features=None, transients=[])
    hook = storyboard.slots[0].model_copy(
        update={
            "assigned_clip_id": "slot_0_clip",
            "crop_start_s": 0.0,
            "crop_end_s": 1.7,
        }
    )
    storyboard = storyboard.model_copy(update={"slots": [hook, *storyboard.slots[1:]]})
    clip_media = {
        "slot_0_clip": MediaInfo(
            path=__import__("pathlib").Path("hook.mp4"),
            duration_s=7.0,
            has_video=True,
        )
    }
    split = apply_hook_inversion_layout(
        storyboard,
        enabled=True,
        payoff_duration_s=1.0,
        clip_media=clip_media,
    )
    hook_start = next(slot for slot in split.slots if slot.role == "hook_start")
    hook_end = next(slot for slot in split.slots if slot.role == "hook_end")
    assert hook_end.crop_end_s == pytest.approx(hook_start.crop_start_s)
    total_source = (hook_end.crop_end_s - hook_end.crop_start_s) + (
        hook_start.crop_end_s - hook_start.crop_start_s
    )
    assert total_source == pytest.approx(1.7, abs=0.01)
    assert hook_start.crop_end_s == pytest.approx(1.7)


def test_hook_inversion_realigns_slot_boundaries_to_downbeats() -> None:
    block = _block(24.0)
    features = _features([10.0, 12.0, 14.0, 16.0, 18.0, 20.0, 22.0, 34.0])
    storyboard = plan_storyboard(block, features=features, transients=[])
    hook = storyboard.slots[0]
    split = apply_hook_inversion_layout(
        storyboard,
        enabled=True,
        payoff_duration_s=2.0,
        features=features,
    )
    hook_start = next(slot for slot in split.slots if slot.role == "hook_start")
    hook_end = next(slot for slot in split.slots if slot.role == "hook_end")
    assert hook_start.target_duration_s == pytest.approx(2.0)
    assert hook_end.target_duration_s == pytest.approx(hook.target_duration_s - 2.0)
    ordered = sorted(split.slots, key=lambda slot: slot.order)
    assert ordered[0].out_start_s == pytest.approx(0.0)
    assert ordered[-1].out_end_s == pytest.approx(split.total_duration_s)
    for left, right in zip(ordered, ordered[1:]):
        assert left.out_end_s == pytest.approx(right.out_start_s)


def test_hook_payoff_downbeats_s_lists_valid_positions() -> None:
    block = _block(17.74)
    features = _features([10.0, 11.857, 13.714, 15.571, 27.74])
    storyboard = plan_storyboard(block, features=features, transients=[])
    hook_budget = storyboard.slots[0].target_duration_s
    positions = hook_payoff_downbeats_s(
        hook_budget,
        features,
        music_start_s=storyboard.music_start_s,
        music_end_s=storyboard.music_end_s,
    )
    assert len(positions) >= 1
    assert all(0.25 <= value <= hook_budget - 0.25 for value in positions)
    snapped = snap_hook_payoff_s(
        3.0,
        hook_budget,
        features,
        music_start_s=storyboard.music_start_s,
        music_end_s=storyboard.music_end_s,
    )
    assert snapped in positions


def test_relayout_beat_aligned_timeline_preserves_total_duration() -> None:
    block = _block(16.0)
    features = _features([10.0, 12.0, 14.0, 16.0, 26.0])
    storyboard = plan_storyboard(block, features=features, transients=[])
    hook = storyboard.slots[0]
    middle = storyboard.slots[1:]
    split_slots = [
        hook.model_copy(
            update={
                "id": "slot_0_hook_start",
                "role": "hook_start",
                "label": "Hook · start",
                "target_duration_s": 1.0,
            }
        ),
        *middle,
        hook.model_copy(
            update={
                "id": "slot_0_hook_end",
                "role": "hook_end",
                "label": "Hook · end",
                "order": len(middle) + 1,
                "target_duration_s": hook.target_duration_s - 1.0,
            }
        ),
    ]
    relaid = relayout_beat_aligned_timeline(
        split_slots,
        total_duration_s=storyboard.total_duration_s,
        features=features,
        music_start_s=storyboard.music_start_s,
        music_end_s=storyboard.music_end_s,
    )
    assert relaid[0].out_start_s == pytest.approx(0.0)
    assert relaid[-1].out_end_s == pytest.approx(storyboard.total_duration_s)
    for left, right in zip(relaid, relaid[1:]):
        assert left.out_end_s == pytest.approx(right.out_start_s)


def test_storyboard_to_segments_keeps_distinct_clip_per_slot() -> None:
    block = _block(16.0)
    storyboard = plan_storyboard(block, features=None, transients=[])
    slots = []
    for index, slot in enumerate(storyboard.slots[:3]):
        slots.append(
            slot.model_copy(
                update={
                    "assigned_clip_id": f"{slot.id}_clip",
                    "crop_start_s": 0.0,
                    "crop_end_s": 2.0,
                }
            )
        )
    storyboard = storyboard.model_copy(update={"slots": slots + storyboard.slots[3:]})
    media = {
        f"slot_{index}_clip": MediaInfo(
            path=__file__,
            duration_s=10.0,
            has_video=True,
        )
        for index in range(3)
    }
    segments, roles, slot_ids = storyboard_to_segments(storyboard, media)
    assert len(segments) == 3
    assert segments[0].source_id == "slot_0_clip"
    assert segments[1].source_id == "slot_1_clip"
    assert segments[2].source_id == "slot_2_clip"
    assert slot_ids == ["slot_0", "slot_1", "slot_2"]


def test_storyboard_to_segments_scales_speed_to_target() -> None:
    block = _block(12.0)
    storyboard = plan_storyboard(block, features=None, transients=[])
    hook = storyboard.slots[0]
    target = hook.target_duration_s
    hook = hook.model_copy(
        update={
            "assigned_clip_id": "slot_0_clip",
            "crop_start_s": 0.0,
            "crop_end_s": target * 1.5,
        }
    )
    storyboard = storyboard.model_copy(update={"slots": [hook, *storyboard.slots[1:]]})
    media = {
        "slot_0_clip": MediaInfo(
            path=__file__,
            duration_s=20.0,
            has_video=True,
        )
    }
    segments, _roles, slot_ids = storyboard_to_segments(storyboard, media)
    assert len(segments) == 1
    assert slot_ids == [hook.id]
    assert segments[0].speed_factor == pytest.approx(1.5)


def test_apply_hook_inversion_preserves_crops_without_reshape() -> None:
    from viral_editor.models import Storyboard, StorySlot

    hook_start = StorySlot(
        id="slot_0_hook_start",
        order=0,
        label="Hook · start",
        role="hook_start",
        out_start_s=0.0,
        out_end_s=2.0,
        target_duration_s=2.0,
        assigned_clip_id="slot_0_clip",
        crop_start_s=18.0,
        crop_end_s=20.0,
    )
    hook_end = StorySlot(
        id="slot_0_hook_end",
        order=1,
        label="Hook · end",
        role="hook_end",
        out_start_s=2.0,
        out_end_s=4.0,
        target_duration_s=2.0,
        assigned_clip_id="slot_0_clip",
        crop_start_s=0.0,
        crop_end_s=18.0,
    )
    storyboard = Storyboard(
        music_block_id="block_a",
        music_start_s=0.0,
        music_end_s=16.0,
        total_duration_s=16.0,
        slots=[hook_start, hook_end],
    )
    resynced = apply_hook_inversion_layout(
        storyboard,
        enabled=True,
        payoff_duration_s=2.0,
        reshape_crops=False,
    )
    start = next(slot for slot in resynced.slots if slot.role == "hook_start")
    end = next(slot for slot in resynced.slots if slot.role == "hook_end")
    assert start.crop_start_s == pytest.approx(18.0)
    assert start.crop_end_s == pytest.approx(20.0)
    assert end.crop_start_s == pytest.approx(0.0)
    assert end.crop_end_s == pytest.approx(18.0)


def test_hook_source_range_respects_user_crop() -> None:
    from viral_editor.audio.storyboard import _hook_source_range_for_split
    from viral_editor.models import StorySlot

    hook_start = StorySlot(
        id="slot_0_hook_start",
        order=0,
        label="Hook · start",
        role="hook_start",
        out_start_s=0.0,
        out_end_s=2.0,
        target_duration_s=2.0,
        assigned_clip_id="slot_0_clip",
        crop_start_s=8.0,
        crop_end_s=10.0,
    )
    hook_end = StorySlot(
        id="slot_0_hook_end",
        order=2,
        label="Hook · end",
        role="hook_end",
        out_start_s=12.0,
        out_end_s=14.0,
        target_duration_s=2.0,
        assigned_clip_id="slot_0_clip",
        crop_start_s=5.0,
        crop_end_s=8.0,
    )
    media = {
        "slot_0_clip": MediaInfo(
            path=Path("clip.mp4"),
            duration_s=30.0,
            has_video=True,
        )
    }
    start, end = _hook_source_range_for_split(
        hook_budget=4.0,
        hook=None,
        hook_start=hook_start,
        hook_end=hook_end,
        clip_media=media,
    )
    assert start == pytest.approx(5.0)
    assert end == pytest.approx(10.0)


def test_hook_split_applies_timestretch_to_build_slot() -> None:
    from viral_editor.models import Storyboard, StorySlot

    hook_start = StorySlot(
        id="slot_0_hook_start",
        order=0,
        label="Hook · start",
        role="hook_start",
        out_start_s=0.0,
        out_end_s=2.0,
        target_duration_s=2.0,
        assigned_clip_id="slot_0_clip",
        crop_start_s=5.0,
        crop_end_s=10.0,
    )
    hook_end = StorySlot(
        id="slot_0_hook_end",
        order=1,
        label="Hook · end",
        role="hook_end",
        out_start_s=2.0,
        out_end_s=4.0,
        target_duration_s=2.0,
        assigned_clip_id="slot_0_clip",
        crop_start_s=0.0,
        crop_end_s=5.0,
    )
    storyboard = Storyboard(
        music_block_id="block_a",
        music_start_s=0.0,
        music_end_s=16.0,
        total_duration_s=16.0,
        slots=[hook_start, hook_end],
    )
    media = {
        "slot_0_clip": MediaInfo(
            path=Path("clip.mp4"),
            duration_s=20.0,
            has_video=True,
        )
    }
    segments, roles, _ = storyboard_to_segments(storyboard, media)
    build_index = roles.index("hook_end")
    start_index = roles.index("hook_start")
    assert segments[build_index].speed_factor == pytest.approx(2.5)
    assert segments[start_index].speed_factor == pytest.approx(2.5)


def test_update_slot_crop_resplits_hook_family() -> None:
    from viral_editor.api.storyboard import update_slot_crop
    from viral_editor.models import Storyboard, StorySlot

    hook_start = StorySlot(
        id="slot_0_hook_start",
        order=0,
        label="Hook · start",
        role="hook_start",
        out_start_s=0.0,
        out_end_s=2.0,
        target_duration_s=2.0,
        assigned_clip_id="slot_0_clip",
        crop_start_s=0.0,
        crop_end_s=2.0,
    )
    hook_end = StorySlot(
        id="slot_0_hook_end",
        order=2,
        label="Hook · end",
        role="hook_end",
        out_start_s=12.0,
        out_end_s=14.0,
        target_duration_s=2.0,
        assigned_clip_id="slot_0_clip",
        crop_start_s=2.0,
        crop_end_s=4.0,
    )
    storyboard = Storyboard(
        music_block_id="block_a",
        music_start_s=0.0,
        music_end_s=16.0,
        total_duration_s=16.0,
        slots=[hook_start, hook_end],
    )
    media = MediaInfo(path=Path("clip.mp4"), duration_s=20.0, has_video=True)
    updated = update_slot_crop(
        storyboard,
        "slot_0_hook_start",
        crop_start_s=4.0,
        crop_end_s=10.0,
        media=media,
        payoff_duration_s=2.0,
    )
    start = next(slot for slot in updated.slots if slot.role == "hook_start")
    end = next(slot for slot in updated.slots if slot.role == "hook_end")
    assert start.crop_end_s - start.crop_start_s == pytest.approx(3.0)
    assert end.crop_end_s - end.crop_start_s == pytest.approx(3.0)
    assert end.crop_end_s == pytest.approx(start.crop_start_s)
    assert start.crop_start_s == pytest.approx(7.0)
    assert end.crop_start_s == pytest.approx(4.0)


def test_storyboard_filled_enough_requires_hook_clip() -> None:
    block = _block(12.0)
    storyboard = plan_storyboard(block, features=None, transients=[])
    assert storyboard_filled_enough(storyboard) is False
    hook = storyboard.slots[0].model_copy(update={"assigned_clip_id": "a"})
    hook_only = storyboard.model_copy(update={"slots": [hook, *storyboard.slots[1:]]})
    assert storyboard_filled_enough(hook_only) is True
    clip = storyboard.slots[1].model_copy(update={"assigned_clip_id": "b"})
    filled = storyboard.model_copy(update={"slots": [hook, clip, *storyboard.slots[2:]]})
    assert storyboard_filled_enough(filled) is True


def test_storyboard_slots_complete_requires_every_slot() -> None:
    block = _block(12.0)
    storyboard = plan_storyboard(block, features=None, transients=[])
    assert storyboard_slots_complete(storyboard) is False

    assigned = [
        slot.model_copy(update={"assigned_clip_id": f"clip_{index}"})
        for index, slot in enumerate(storyboard.slots)
    ]
    assert storyboard_slots_complete(storyboard.model_copy(update={"slots": assigned})) is True

    partial = assigned.copy()
    partial[-1] = partial[-1].model_copy(update={"assigned_clip_id": None})
    assert storyboard_slots_complete(storyboard.model_copy(update={"slots": partial})) is False


def test_update_slot_transform_rotates_and_sets_cover() -> None:
    from viral_editor.api.storyboard import update_slot_transform
    from viral_editor.models import SpatialCrop

    block = _block(12.0)
    storyboard = plan_storyboard(block, features=None, transients=[])
    hook = storyboard.slots[0].model_copy(update={"assigned_clip_id": "slot_0_clip"})
    storyboard = storyboard.model_copy(update={"slots": [hook, *storyboard.slots[1:]]})
    updated = update_slot_transform(
        storyboard,
        hook.id,
        rotation_deg=90,
        spatial_crop=SpatialCrop(x=0.1, y=0.0, w=0.5, h=0.9),
        update_spatial_crop=True,
    )
    slot = updated.slots[0]
    assert slot.rotation_deg == 90
    assert slot.spatial_crop is not None
    assert slot.spatial_crop.w == pytest.approx(0.5)


def test_assign_slot_clip_keeps_spatial_crop() -> None:
    from viral_editor.api.storyboard import assign_slot_clip
    from viral_editor.models import MediaInfo, SpatialCrop

    block = _block(12.0)
    storyboard = plan_storyboard(block, features=None, transients=[])
    hook = storyboard.slots[0]
    media = MediaInfo(path=__file__, duration_s=10.0, has_video=True, width=1920, height=1080)
    crop = SpatialCrop(x=0.1, y=0.05, w=0.45, h=0.8)
    updated = assign_slot_clip(
        storyboard,
        hook.id,
        clip_id=f"{hook.id}_clip",
        filename="hook.mp4",
        crop_start_s=0.0,
        crop_end_s=2.0,
        media=media,
        rotation_deg=90,
        spatial_crop=crop,
    )
    slot = next(item for item in updated.slots if item.id == hook.id)
    assert slot.spatial_crop == crop
    assert slot.rotation_deg == 90


def test_remap_fx_events_for_composite_skips_unassigned_slots() -> None:
    from viral_editor.audio.storyboard import (
        remap_fx_events_for_composite,
        storyboard_time_to_composite_time,
    )
    from viral_editor.models import FxEvent, Storyboard, StorySlot

    hook_start = StorySlot(
        id="slot_0_hook_start",
        order=0,
        label="Hook · start",
        role="hook_start",
        out_start_s=0.0,
        out_end_s=2.0,
        target_duration_s=2.0,
        transition_in="cut",
        assigned_clip_id="slot_0_clip",
    )
    middle = StorySlot(
        id="slot_1",
        order=1,
        label="Clip 1",
        role="clip",
        out_start_s=2.0,
        out_end_s=6.0,
        target_duration_s=4.0,
        transition_in="xfade",
        assigned_clip_id=None,
    )
    hook_end = StorySlot(
        id="slot_0_hook_end",
        order=2,
        label="Hook · end",
        role="hook_end",
        out_start_s=6.0,
        out_end_s=8.0,
        target_duration_s=2.0,
        transition_in="xfade",
        assigned_clip_id="slot_0_clip",
    )
    storyboard = Storyboard(
        music_block_id="block_a",
        music_start_s=0.0,
        music_end_s=8.0,
        total_duration_s=8.0,
        slots=[hook_start, middle, hook_end],
    )

    events = [
        FxEvent(timestamp_s=1.0, kind="zoom", magnitude=1.07, decay_frames=4),
        FxEvent(timestamp_s=3.0, kind="zoom", magnitude=1.06, decay_frames=4),
        FxEvent(timestamp_s=7.0, kind="rotate", magnitude=1.2, decay_frames=4),
    ]
    remapped = remap_fx_events_for_composite(events, storyboard)

    assert len(remapped) == 2
    assert remapped[0].kind == "zoom"
    assert remapped[0].timestamp_s == pytest.approx(1.0)
    assert remapped[1].kind == "rotate"
    assert remapped[1].timestamp_s == pytest.approx(2.75)
    assert storyboard_time_to_composite_time(storyboard, 3.0) is None


def test_reuse_storyboard_assignments_carries_slots_to_new_block() -> None:
    from viral_editor.api.storyboard import reuse_storyboard_assignments
    from viral_editor.models import SpatialCrop, Storyboard, StorySlot

    previous = Storyboard(
        music_block_id="block_a",
        music_start_s=0.0,
        music_end_s=8.0,
        total_duration_s=8.0,
        slots=[
            StorySlot(
                id="slot_0_hook_start",
                order=0,
                label="Hook · start",
                role="hook_start",
                out_start_s=0.0,
                out_end_s=2.0,
                target_duration_s=2.0,
                assigned_clip_id="hook_clip",
                crop_start_s=7.0,
                crop_end_s=10.0,
                clip_filename="hook.mp4",
                rotation_deg=90,
                spatial_crop=SpatialCrop(x=0.1, y=0.0, w=0.5, h=0.9),
            ),
            StorySlot(
                id="slot_1",
                order=1,
                label="Clip 1",
                role="clip",
                out_start_s=2.0,
                out_end_s=6.0,
                target_duration_s=4.0,
                assigned_clip_id="body_clip",
                crop_start_s=3.0,
                crop_end_s=9.0,
                clip_filename="body.mp4",
            ),
            StorySlot(
                id="slot_0_hook_end",
                order=2,
                label="Hook · end",
                role="hook_end",
                out_start_s=6.0,
                out_end_s=8.0,
                target_duration_s=2.0,
                assigned_clip_id="hook_clip",
                crop_start_s=0.0,
                crop_end_s=7.0,
                clip_filename="hook.mp4",
                rotation_deg=90,
                spatial_crop=SpatialCrop(x=0.1, y=0.0, w=0.5, h=0.9),
            ),
        ],
    )
    new_block = Storyboard(
        music_block_id="block_b",
        music_start_s=20.0,
        music_end_s=28.0,
        total_duration_s=8.0,
        slots=[
            StorySlot(
                id="slot_0_hook_start",
                order=0,
                label="Hook · start",
                role="hook_start",
                out_start_s=0.0,
                out_end_s=2.0,
                target_duration_s=2.0,
            ),
            StorySlot(
                id="slot_1",
                order=1,
                label="Clip 1",
                role="punch",
                out_start_s=2.0,
                out_end_s=5.5,
                target_duration_s=3.5,
            ),
            StorySlot(
                id="slot_2",
                order=2,
                label="Clip 2",
                role="clip",
                out_start_s=5.5,
                out_end_s=7.0,
                target_duration_s=1.5,
            ),
            StorySlot(
                id="slot_0_hook_end",
                order=3,
                label="Hook · end",
                role="hook_end",
                out_start_s=7.0,
                out_end_s=8.0,
                target_duration_s=1.0,
            ),
        ],
    )

    reused = reuse_storyboard_assignments(new_block, previous)
    hook_start = reused.slots[0]
    body_1 = reused.slots[1]
    body_2 = reused.slots[2]
    hook_end = reused.slots[3]

    assert hook_start.assigned_clip_id == "hook_clip"
    assert hook_start.crop_start_s == pytest.approx(7.0)
    assert body_1.assigned_clip_id == "body_clip"
    assert body_1.crop_end_s == pytest.approx(9.0)
    assert body_2.assigned_clip_id is None
    assert hook_end.assigned_clip_id == "hook_clip"
    assert hook_end.rotation_deg == 90


def test_persist_storyboard_variant_restores_block_specific_assignments(tmp_path: Path) -> None:
    from viral_editor.api.storyboard import (
        load_storyboard_variants,
        persist_storyboard_variant,
        reuse_storyboard_assignments,
    )
    from viral_editor.models import Storyboard, StorySlot

    block_a = Storyboard(
        music_block_id="block_a",
        music_start_s=0.0,
        music_end_s=8.0,
        total_duration_s=8.0,
        slots=[
            StorySlot(
                id="slot_0_hook_start",
                order=0,
                label="Hook · start",
                role="hook_start",
                out_start_s=0.0,
                out_end_s=2.0,
                target_duration_s=2.0,
                assigned_clip_id="a_hook",
                crop_start_s=8.0,
                crop_end_s=10.0,
            ),
        ],
    )
    block_b = Storyboard(
        music_block_id="block_b",
        music_start_s=20.0,
        music_end_s=28.0,
        total_duration_s=8.0,
        slots=[
            StorySlot(
                id="slot_0_hook_start",
                order=0,
                label="Hook · start",
                role="hook_start",
                out_start_s=0.0,
                out_end_s=2.0,
                target_duration_s=2.0,
                assigned_clip_id="b_hook",
                crop_start_s=1.0,
                crop_end_s=3.0,
            ),
        ],
    )

    persist_storyboard_variant(tmp_path, block_a)
    persist_storyboard_variant(tmp_path, block_b)
    variants = load_storyboard_variants(tmp_path)

    restored = reuse_storyboard_assignments(
        Storyboard(
            music_block_id="block_a",
            music_start_s=0.0,
            music_end_s=8.0,
            total_duration_s=8.0,
            slots=[
                StorySlot(
                    id="slot_0_hook_start",
                    order=0,
                    label="Hook · start",
                    role="hook_start",
                    out_start_s=0.0,
                    out_end_s=2.0,
                    target_duration_s=2.0,
                ),
            ],
        ),
        variants["block_a"],
    )

    assert restored.slots[0].assigned_clip_id == "a_hook"
    assert restored.slots[0].crop_start_s == pytest.approx(8.0)


_SALIENT_HOP = 512
_SALIENT_SR = 22050


def _frame_at(time_s: float) -> int:
    return int(time_s * _SALIENT_SR / _SALIENT_HOP)


def _scope_with_peaks(
    peak_times_s: list[float],
    *,
    duration_s: float = 16.0,
) -> dict[str, np.ndarray]:
    """Synthetic scope lanes with local maxima at ``peak_times_s``."""
    n = _frame_at(duration_s) + 20
    rms = np.full(n, 0.15, dtype=np.float32)
    drop_salience = np.zeros(n, dtype=np.float32)
    surge = np.zeros(n, dtype=np.float32)
    build = np.zeros(n, dtype=np.float32)
    flux_low = np.zeros(n, dtype=np.float32)
    for time_s in peak_times_s:
        center = _frame_at(time_s)
        for offset in range(-4, 5):
            frame = center + offset
            if 0 <= frame < n:
                val = 0.55 + 0.45 * (1.0 - abs(offset) / 5.0)
                rms[frame] = max(float(rms[frame]), 0.2 + 0.75 * val)
                drop_salience[frame] = max(float(drop_salience[frame]), val)
                surge[frame] = max(float(surge[frame]), val * 0.95)
                build[frame] = max(float(build[frame]), val * 0.8)
    return {
        "rms": rms,
        "drop_salience": drop_salience,
        "surge": surge,
        "build": build,
        "flux_low": flux_low,
    }


def _downbeats_every(step_s: float, duration_s: float) -> list[float]:
    count = int(duration_s / step_s) + 1
    return [round(index * step_s, 6) for index in range(count)]


def test_salient_boundaries_align_to_injected_peaks() -> None:
    """Cycle A: cuts land near injected drop/surge peaks."""
    duration_s = 16.0
    scope = _scope_with_peaks([4.0, 8.5], duration_s=duration_s)
    downbeats = _downbeats_every(2.0, duration_s)
    plan = _salient_boundaries(
        0.0,
        duration_s,
        downbeats=downbeats,
        scope_lanes=scope,
        absolute_downbeats=downbeats,
        soft_count_range=(2, 6),
    )
    interior = plan.boundaries[1:-1]
    assert any(abs(boundary - 4.0) <= 0.2 for boundary in interior)
    assert any(abs(boundary - 8.5) <= 0.2 for boundary in interior)


def test_salient_boundaries_enforce_cadence_limits() -> None:
    """Cycle B: spans stay within viral floor/ceiling; large gaps subdivide."""
    duration_s = 18.0
    scope = _scope_with_peaks([3.1, 3.3, 15.5], duration_s=duration_s)
    downbeats = _downbeats_every(1.0, duration_s)
    plan = _salient_boundaries(
        0.0,
        duration_s,
        downbeats=downbeats,
        scope_lanes=scope,
        absolute_downbeats=downbeats,
        soft_count_range=(2, 8),
    )
    spans = [
        plan.boundaries[index + 1] - plan.boundaries[index]
        for index in range(len(plan.boundaries) - 1)
    ]
    assert all(span >= 1.5 - 1e-3 for span in spans)
    assert all(span <= 6.5 + 1e-3 for span in spans)
    assert len(plan.boundaries) >= 4


def test_salient_boundaries_respect_soft_count_range() -> None:
    """Cycle C: slot count stays inside chip soft band."""
    duration_s = 16.0
    scope = _scope_with_peaks([3.5, 7.0, 10.5, 13.5], duration_s=duration_s)
    downbeats = _downbeats_every(1.0, duration_s)
    lo, hi = _soft_count_range(duration_s, 4)
    assert lo == 3
    assert hi == 6
    plan = _salient_boundaries(
        0.0,
        duration_s,
        downbeats=downbeats,
        scope_lanes=scope,
        absolute_downbeats=downbeats,
        soft_count_range=(lo, hi),
    )
    slot_count = len(plan.boundaries) - 1
    assert lo <= slot_count <= hi


def test_plan_storyboard_middle_slots_non_uniform_with_scope_lanes() -> None:
    """Cycle D: salience-driven layout yields unequal slot durations."""
    duration_s = 18.0
    block = MusicBlock(
        id="salient",
        start_s=0.0,
        end_s=duration_s,
        duration_s=duration_s,
        score=0.9,
        drop_count=2,
        transient_count=4,
        label="Test",
        reason="test",
        loop_quality=0.8,
        phrase_bars=4,
    )
    scope = _scope_with_peaks([3.2, 6.0, 12.5], duration_s=duration_s)
    downbeats = _downbeats_every(1.0, duration_s)
    features = _features(downbeats)
    storyboard = plan_storyboard(
        block,
        features=features,
        transients=[],
        scope_lanes=scope,
        target_slot_count=4,
    )
    durations = [slot.target_duration_s for slot in storyboard.slots]
    assert len(durations) >= 3
    assert max(durations) - min(durations) > 0.8


def test_slot_rationales_describe_salient_events() -> None:
    """Cycle E: rationales reference energy/surge events, not generic downbeats."""
    duration_s = 16.0
    scope = _scope_with_peaks([4.0, 8.5], duration_s=duration_s)
    downbeats = _downbeats_every(2.0, duration_s)
    storyboard = plan_storyboard(
        _short_block(duration_s),
        features=_features(downbeats),
        transients=[],
        scope_lanes=scope,
        target_slot_count=4,
    )
    body_reasons = [
        slot.rationale
        for slot in storyboard.slots[1:]
        if slot.rationale
    ]
    assert body_reasons
    assert any(
        "peak" in reason.lower() or "surge" in reason.lower() or "flux" in reason.lower()
        for reason in body_reasons
    )
