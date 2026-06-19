"""Storyboard artifact helpers and refresh logic."""

from __future__ import annotations

from pathlib import Path

from viral_editor.audio.block_planner import selected_block
from viral_editor.audio.features import BeatSyncFeatures
from viral_editor.audio.storyboard import merge_storyboard_updates, plan_storyboard
from viral_editor.config import JobConfig
from viral_editor.ingest.loader import probe_media
from viral_editor.models import ClipInput, MediaInfo, SpatialCrop, Storyboard, StorySlot, write_artifact
from viral_editor.video.clip_reel import normalize_crop_range


def load_storyboard(temp_dir: Path) -> Storyboard | None:
    path = temp_dir / "storyboard.json"
    if not path.is_file():
        return None
    return Storyboard.model_validate_json(path.read_text(encoding="utf-8"))


def persist_storyboard(temp_dir: Path, storyboard: Storyboard) -> Path:
    return write_artifact(storyboard, "storyboard", temp_dir)


def persist_storyboard_for_job(
    config: JobConfig,
    temp_dir: Path,
    *,
    sections=None,
) -> Storyboard | None:
    """Build and persist a storyboard from the current music selection."""
    del sections
    from viral_editor.api.music import load_audio_timeline, load_beat_features, load_music_blocks

    try:
        block_plan = load_music_blocks(temp_dir)
        timeline = load_audio_timeline(temp_dir)
    except FileNotFoundError:
        return None

    block = selected_block(block_plan)
    if block is None:
        return None

    features = load_beat_features(temp_dir)
    storyboard = plan_storyboard(
        block,
        features=features,
        transients=timeline.transients,
    )
    persist_storyboard(temp_dir, storyboard)
    return storyboard


def refresh_storyboard_after_music(
    config: JobConfig,
    temp_dir: Path,
) -> Storyboard | None:
    return persist_storyboard_for_job(config, temp_dir)


def apply_storyboard_patch(
    storyboard: Storyboard,
    *,
    slots: list[StorySlot] | None = None,
    loop_to_hook: bool | None = None,
) -> Storyboard:
    updated = storyboard
    if slots is not None:
        updated = merge_storyboard_updates(updated, slots)
    if loop_to_hook is not None:
        updated = updated.model_copy(update={"loop_to_hook": loop_to_hook})
    return updated


def assign_slot_clip(
    storyboard: Storyboard,
    slot_id: str,
    *,
    clip_id: str,
    filename: str,
    crop_start_s: float | None,
    crop_end_s: float | None,
    media: MediaInfo,
    rotation_deg: int = 0,
    fit_mode: str = "contain",
    spatial_crop: SpatialCrop | None = None,
) -> Storyboard:
    clip = ClipInput(
        id=clip_id,
        path=media.path,
        order=0,
        crop_start_s=crop_start_s,
        crop_end_s=crop_end_s,
    )
    norm_start, norm_end = normalize_crop_range(clip, media)
    normalized_rot = int(rotation_deg) % 360
    if normalized_rot not in (0, 90, 180, 270):
        normalized_rot = 0
    slots = []
    for slot in storyboard.slots:
        if slot.id != slot_id:
            slots.append(slot)
            continue
        slots.append(
            slot.model_copy(
                update={
                    "assigned_clip_id": clip_id,
                    "crop_start_s": norm_start,
                    "crop_end_s": norm_end,
                    "clip_filename": filename,
                    "rotation_deg": normalized_rot,
                    "fit_mode": fit_mode,
                    "spatial_crop": spatial_crop,
                }
            )
        )
    return storyboard.model_copy(update={"slots": slots})


def update_slot_crop(
    storyboard: Storyboard,
    slot_id: str,
    *,
    crop_start_s: float,
    crop_end_s: float,
    media: MediaInfo,
) -> Storyboard:
    clip = ClipInput(
        id=f"{slot_id}_clip",
        path=media.path,
        order=0,
        crop_start_s=crop_start_s,
        crop_end_s=crop_end_s,
    )
    norm_start, norm_end = normalize_crop_range(clip, media)
    slots = []
    for slot in storyboard.slots:
        if slot.id != slot_id:
            slots.append(slot)
            continue
        if slot.assigned_clip_id is None:
            raise ValueError(f"Slot {slot_id!r} has no assigned clip")
        slots.append(
            slot.model_copy(
                update={
                    "crop_start_s": norm_start,
                    "crop_end_s": norm_end,
                }
            )
        )
    return storyboard.model_copy(update={"slots": slots})


def update_slot_transform(
    storyboard: Storyboard,
    slot_id: str,
    *,
    rotation_deg: int | None = None,
    fit_mode: str | None = None,
    spatial_crop: SpatialCrop | None = None,
    update_spatial_crop: bool = False,
) -> Storyboard:
    slots = []
    for slot in storyboard.slots:
        if slot.id != slot_id:
            slots.append(slot)
            continue
        if slot.assigned_clip_id is None:
            raise ValueError(f"Slot {slot_id!r} has no assigned clip")
        updates: dict[str, object] = {}
        if rotation_deg is not None:
            normalized = int(rotation_deg) % 360
            if normalized not in (0, 90, 180, 270):
                raise ValueError("rotation_deg must be a multiple of 90")
            updates["rotation_deg"] = normalized
        if fit_mode is not None:
            updates["fit_mode"] = fit_mode
        if update_spatial_crop:
            updates["spatial_crop"] = spatial_crop
        if not updates:
            slots.append(slot)
            continue
        slots.append(slot.model_copy(update=updates))
    return storyboard.model_copy(update={"slots": slots})


def clear_slot_clip(storyboard: Storyboard, slot_id: str) -> Storyboard:
    slots = []
    for slot in storyboard.slots:
        if slot.id != slot_id:
            slots.append(slot)
            continue
        slots.append(
            slot.model_copy(
                update={
                    "assigned_clip_id": None,
                    "crop_start_s": None,
                    "crop_end_s": None,
                    "clip_filename": None,
                    "rotation_deg": 0,
                    "fit_mode": "contain",
                    "spatial_crop": None,
                }
            )
        )
    return storyboard.model_copy(update={"slots": slots})


def clip_media_for_storyboard(config: JobConfig) -> dict[str, MediaInfo]:
    media: dict[str, MediaInfo] = {}
    for clip in config.clips:
        if clip.path.is_file():
            media[clip.id] = probe_media(clip.path)
    return media


def sync_config_clips_from_storyboard(
    config: JobConfig,
    storyboard: Storyboard,
) -> JobConfig:
    """Ensure config.clips contains every assigned clip id."""
    existing = {clip.id: clip for clip in config.clips}
    for slot in storyboard.slots:
        if slot.assigned_clip_id is None:
            continue
        clip = existing.get(slot.assigned_clip_id)
        if clip is None:
            continue
        existing[slot.assigned_clip_id] = clip.model_copy(
            update={
                "crop_start_s": slot.crop_start_s,
                "crop_end_s": slot.crop_end_s,
                "rotation_deg": slot.rotation_deg,
                "fit_mode": slot.fit_mode,
                "spatial_crop": slot.spatial_crop,
            }
        )
    return config.model_copy(update={"clips": sorted(existing.values(), key=lambda c: c.order)})
