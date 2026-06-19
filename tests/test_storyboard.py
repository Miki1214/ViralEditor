"""Tests for storyboard planner."""

from __future__ import annotations

import numpy as np
import pytest

from viral_editor.audio.features import BeatFeaturesMeta, BeatSyncFeatures
from viral_editor.audio.storyboard import (
    plan_storyboard,
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
    segments = storyboard_to_segments(storyboard, media)
    assert len(segments) == 1
    assert segments[0].source_id == "slot_0_clip"
    assert segments[0].src_end_s - segments[0].src_start_s == pytest.approx(4.0)


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
    segments = storyboard_to_segments(storyboard, media)
    assert len(segments) == 1
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
