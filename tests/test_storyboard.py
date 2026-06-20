"""Tests for storyboard planner."""

from __future__ import annotations

import numpy as np
import pytest

from viral_editor.audio.features import BeatFeaturesMeta, BeatSyncFeatures
from viral_editor.audio.storyboard import (
    apply_hook_inversion_layout,
    hook_payoff_downbeats_s,
    plan_storyboard,
    relayout_beat_aligned_timeline,
    snap_hook_payoff_s,
    storyboard_filled_enough,
    storyboard_to_segments,
)
from viral_editor.models import MediaInfo, MusicBlock, Transient


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
    assert len(storyboard.slots) >= 3
    assert storyboard.slots[0].role == "hook"
    assert storyboard.loop_to_hook is True
    assert storyboard.total_duration_s == pytest.approx(24.0)


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
    assert hook_start.crop_end_s - hook_start.crop_start_s == pytest.approx(
        hook_start.target_duration_s,
        abs=0.01,
    )
    assert hook_end.crop_end_s - hook_end.crop_start_s == pytest.approx(
        hook_end.target_duration_s,
        abs=0.01,
    )
    assert hook_end.crop_end_s == pytest.approx(hook_start.crop_start_s)


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
    assert segments[0].out_end_s - segments[0].out_start_s == pytest.approx(target)


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
