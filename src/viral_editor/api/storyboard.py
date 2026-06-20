"""Storyboard artifact helpers and refresh logic."""

from __future__ import annotations

from pathlib import Path

from viral_editor.audio.block_planner import selected_block
from viral_editor.audio.features import BeatSyncFeatures
from viral_editor.audio.storyboard import (
    apply_hook_inversion_layout,
    hook_payoff_downbeats_s,
    merge_storyboard_updates,
    plan_storyboard,
)
from viral_editor.config import JobConfig, TeaserConfig
from viral_editor.ingest.loader import probe_media
from viral_editor.editing.retention_policy import select_payoff_downbeat_s
from viral_editor.models import ClipInput, MediaInfo, SpatialCrop, Storyboard, StorySlot, write_artifact
from viral_editor.video.clip_reel import normalize_crop_range
from viral_editor.video.teaser import split_hook_crop_by_output_ratio


def load_storyboard(temp_dir: Path) -> Storyboard | None:
    path = temp_dir / "storyboard.json"
    if not path.is_file():
        return None
    return Storyboard.model_validate_json(path.read_text(encoding="utf-8"))


def persist_storyboard(temp_dir: Path, storyboard: Storyboard) -> Path:
    return write_artifact(storyboard, "storyboard", temp_dir)


def refresh_hook_inversion_layout(
    storyboard: Storyboard,
    config: JobConfig,
    temp_dir: Path | None = None,
    *,
    reshape_crops: bool = False,
) -> Storyboard:
    """Split or merge hook slots to match retention FX settings."""
    features = None
    scope_lanes = None
    if temp_dir is not None:
        try:
            from viral_editor.api.music import load_beat_features, load_scope_lanes

            features = load_beat_features(temp_dir)
            scope_lanes = load_scope_lanes(temp_dir)
        except FileNotFoundError:
            features = None
            scope_lanes = None
    return apply_hook_inversion_layout(
        storyboard,
        enabled=config.teaser.enabled,
        payoff_duration_s=config.teaser.duration_s,
        features=features,
        scope_lanes=scope_lanes,
        clip_media=clip_media_for_storyboard(config, storyboard),
        reshape_crops=reshape_crops,
    )


def sync_teaser_duration_from_layout(
    config: JobConfig,
    storyboard: Storyboard,
) -> JobConfig:
    """Keep teaser.duration_s aligned with downbeat-snapped hook start slot."""
    if not config.teaser.enabled:
        return config
    hook_start = next(
        (slot for slot in storyboard.slots if slot.role == "hook_start"),
        None,
    )
    if hook_start is None:
        return config
    snapped = round(hook_start.target_duration_s, 6)
    if abs(snapped - config.teaser.duration_s) < 1e-3:
        return config
    return config.model_copy(
        update={"teaser": config.teaser.model_copy(update={"duration_s": snapped})}
    )


def sync_storyboard_hook_layout(
    storyboard: Storyboard,
    config: JobConfig,
    temp_dir: Path | None = None,
) -> Storyboard:
    """Reconcile hook inversion layout and downbeat alignment with current settings."""
    split = any(slot.role in ("hook_start", "hook_end") for slot in storyboard.slots)
    if config.teaser.enabled or split:
        return refresh_hook_inversion_layout(
            storyboard,
            config,
            temp_dir=temp_dir,
            reshape_crops=False,
        )
    return storyboard


def hook_output_budget_s(storyboard: Storyboard) -> float:
    hook = next((slot for slot in storyboard.slots if slot.role == "hook"), None)
    if hook is not None:
        return hook.target_duration_s
    hook_start = next((slot for slot in storyboard.slots if slot.role == "hook_start"), None)
    hook_end = next((slot for slot in storyboard.slots if slot.role == "hook_end"), None)
    return (hook_start.target_duration_s if hook_start else 0.0) + (
        hook_end.target_duration_s if hook_end else 0.0
    )


def teaser_settings_response(
    config: JobConfig,
    storyboard: Storyboard,
    temp_dir: Path | None = None,
) -> dict[str, object]:
    """Build teaser settings payload including valid payoff downbeat positions."""
    teaser: TeaserConfig = config.teaser
    payoff_downbeats: list[float] = []
    if teaser.enabled:
        features: BeatSyncFeatures | None = None
        scope_lanes = None
        if temp_dir is not None:
            try:
                from viral_editor.api.music import load_beat_features, load_scope_lanes

                features = load_beat_features(temp_dir)
                scope_lanes = load_scope_lanes(temp_dir)
            except FileNotFoundError:
                features = None
                scope_lanes = None
        hook_budget = hook_output_budget_s(storyboard)
        payoff_downbeats = hook_payoff_downbeats_s(
            hook_budget,
            features,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
        )
        if features is not None and payoff_downbeats:
            preferred = select_payoff_downbeat_s(
                scope_lanes,
                features.downbeat_times_s.tolist(),
                window_start_s=storyboard.music_start_s,
                window_end_s=storyboard.music_end_s,
                hook_budget_s=hook_budget,
            )
            if preferred not in payoff_downbeats:
                payoff_downbeats.append(preferred)
            payoff_downbeats = sorted(set(round(t, 6) for t in payoff_downbeats))
    return {
        "enabled": teaser.enabled,
        "tail_fraction": teaser.tail_fraction,
        "duration_s": teaser.duration_s,
        "mask": teaser.mask,
        "payoff_downbeats_s": payoff_downbeats,
    }


def _is_hook_family_role(role: str) -> bool:
    return role in ("hook", "hook_start", "hook_end")


def hook_unified_crop_range(storyboard: Storyboard) -> tuple[float, float] | None:
    """Return the contiguous source crop spanning hook / hook_start + hook_end."""
    hook = next((slot for slot in storyboard.slots if slot.role == "hook"), None)
    hook_start = next((slot for slot in storyboard.slots if slot.role == "hook_start"), None)
    hook_end = next((slot for slot in storyboard.slots if slot.role == "hook_end"), None)
    if hook is not None:
        if hook.crop_start_s is None or hook.crop_end_s is None:
            return None
        return hook.crop_start_s, hook.crop_end_s
    if hook_start is None or hook_end is None:
        return None
    starts = [
        slot.crop_start_s
        for slot in (hook_start, hook_end)
        if slot.crop_start_s is not None
    ]
    ends = [
        slot.crop_end_s
        for slot in (hook_start, hook_end)
        if slot.crop_end_s is not None
    ]
    if not starts or not ends:
        return None
    return min(starts), max(ends)


def _resplit_hook_family_crops(
    storyboard: Storyboard,
    *,
    crop_start_s: float,
    crop_end_s: float,
    payoff_duration_s: float,
) -> Storyboard:
    """Apply a unified hook source window and re-split payoff/build slot crops."""
    hook_start = next((slot for slot in storyboard.slots if slot.role == "hook_start"), None)
    hook_end = next((slot for slot in storyboard.slots if slot.role == "hook_end"), None)
    if hook_start is None or hook_end is None:
        return storyboard

    payoff_out = payoff_duration_s if payoff_duration_s is not None else hook_start.target_duration_s
    build_out = hook_end.target_duration_s
    head, tail = split_hook_crop_by_output_ratio(
        crop_start_s,
        crop_end_s,
        payoff_out,
        build_out,
    )
    slots: list[StorySlot] = []
    for slot in storyboard.slots:
        if slot.role == "hook_start":
            slots.append(
                slot.model_copy(
                    update={
                        "crop_start_s": round(tail[0], 6),
                        "crop_end_s": round(tail[1], 6),
                    }
                )
            )
        elif slot.role == "hook_end":
            slots.append(
                slot.model_copy(
                    update={
                        "crop_start_s": round(head[0], 6),
                        "crop_end_s": round(head[1], 6),
                    }
                )
            )
        else:
            slots.append(slot)
    return storyboard.model_copy(update={"slots": slots})


def hook_family_assigned_clip_id(storyboard: Storyboard, slot: StorySlot) -> str | None:
    if slot.assigned_clip_id:
        return slot.assigned_clip_id
    if not _is_hook_family_role(slot.role):
        return None
    for other in storyboard.slots:
        if _is_hook_family_role(other.role) and other.assigned_clip_id:
            return other.assigned_clip_id
    return None


def hook_clip_id_for_slot(slot_id: str, role: str) -> str:
    """Stable clip id shared by hook / hook_start / hook_end slots."""
    if _is_hook_family_role(role):
        root = slot_id.replace("_hook_start", "").replace("_hook_end", "")
        return f"{root}_clip"
    return f"{slot_id}_clip"


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
    scope_lanes = None
    try:
        from viral_editor.api.music import load_scope_lanes

        scope_lanes = load_scope_lanes(temp_dir)
    except FileNotFoundError:
        scope_lanes = None

    storyboard = plan_storyboard(
        block,
        features=features,
        transients=timeline.transients,
        scope_lanes=scope_lanes,
    )
    storyboard = refresh_hook_inversion_layout(
        storyboard,
        config,
        temp_dir=temp_dir,
        reshape_crops=True,
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
    target = next(slot for slot in storyboard.slots if slot.id == slot_id)
    assignment = {
        "assigned_clip_id": clip_id,
        "crop_start_s": norm_start,
        "crop_end_s": norm_end,
        "clip_filename": filename,
        "rotation_deg": normalized_rot,
        "fit_mode": fit_mode,
        "spatial_crop": spatial_crop,
    }
    if _is_hook_family_role(target.role):
        assignment["crop_start_s"] = 0.0
        assignment["crop_end_s"] = round(media.duration_s, 6)
    slots = []
    for slot in storyboard.slots:
        if slot.id == slot_id or (
            _is_hook_family_role(target.role) and _is_hook_family_role(slot.role)
        ):
            slots.append(slot.model_copy(update=assignment))
        else:
            slots.append(slot)
    updated = storyboard.model_copy(update={"slots": slots})
    if _is_hook_family_role(target.role):
        hook_start = next((slot for slot in updated.slots if slot.role == "hook_start"), None)
        hook_end = next((slot for slot in updated.slots if slot.role == "hook_end"), None)
        if hook_start is not None and hook_end is not None:
            return _resplit_hook_family_crops(
                updated,
                crop_start_s=0.0,
                crop_end_s=round(media.duration_s, 6),
                payoff_duration_s=hook_start.target_duration_s,
            )
    return updated


def update_slot_crop(
    storyboard: Storyboard,
    slot_id: str,
    *,
    crop_start_s: float,
    crop_end_s: float,
    media: MediaInfo,
    payoff_duration_s: float | None = None,
) -> Storyboard:
    target = next(slot for slot in storyboard.slots if slot.id == slot_id)
    clip = ClipInput(
        id=f"{slot_id}_clip",
        path=media.path,
        order=0,
        crop_start_s=crop_start_s,
        crop_end_s=crop_end_s,
    )
    norm_start, norm_end = normalize_crop_range(clip, media)
    hook_start = next((slot for slot in storyboard.slots if slot.role == "hook_start"), None)
    hook_end = next((slot for slot in storyboard.slots if slot.role == "hook_end"), None)

    if (
        _is_hook_family_role(target.role)
        and hook_start is not None
        and hook_end is not None
    ):
        payoff_d = payoff_duration_s if payoff_duration_s is not None else hook_start.target_duration_s
        return _resplit_hook_family_crops(
            storyboard,
            crop_start_s=norm_start,
            crop_end_s=norm_end,
            payoff_duration_s=payoff_d,
        )

    if target.assigned_clip_id is None:
        raise ValueError(f"Slot {slot_id!r} has no assigned clip")

    slots = []
    for slot in storyboard.slots:
        if slot.id != slot_id:
            slots.append(slot)
            continue
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
    updated = storyboard.model_copy(update={"slots": slots})
    target = next(item for item in updated.slots if item.id == slot_id)
    if not _is_hook_family_role(target.role):
        return updated
    synced = []
    for slot in updated.slots:
        if slot.id == slot_id:
            synced.append(slot)
            continue
        if _is_hook_family_role(slot.role):
            synced.append(
                slot.model_copy(
                    update={
                        "rotation_deg": target.rotation_deg,
                        "fit_mode": target.fit_mode,
                        "spatial_crop": target.spatial_crop,
                    }
                )
            )
        else:
            synced.append(slot)
    return storyboard.model_copy(update={"slots": synced})


def clear_slot_clip(storyboard: Storyboard, slot_id: str) -> Storyboard:
    target = next((slot for slot in storyboard.slots if slot.id == slot_id), None)
    clear_roles = (
        {"hook", "hook_start", "hook_end"}
        if target is not None and _is_hook_family_role(target.role)
        else {target.role if target else ""}
    )
    cleared = {
        "assigned_clip_id": None,
        "crop_start_s": None,
        "crop_end_s": None,
        "clip_filename": None,
        "rotation_deg": 0,
        "fit_mode": "contain",
        "spatial_crop": None,
    }
    slots = []
    for slot in storyboard.slots:
        if slot.id == slot_id or (
            target is not None
            and _is_hook_family_role(target.role)
            and slot.role in clear_roles
        ):
            slots.append(slot.model_copy(update=cleared))
        else:
            slots.append(slot)
    return storyboard.model_copy(update={"slots": slots})


def clip_media_for_storyboard(
    config: JobConfig,
    storyboard: Storyboard | None = None,
) -> dict[str, MediaInfo]:
    """Probe media for every clip referenced by config and/or storyboard slots."""
    clips_by_id = {clip.id: clip for clip in config.clips}
    clip_ids: set[str] = set(clips_by_id)
    if storyboard is not None:
        clip_ids.update(
            slot.assigned_clip_id
            for slot in storyboard.slots
            if slot.assigned_clip_id
        )
    media: dict[str, MediaInfo] = {}
    for clip_id in sorted(clip_ids):
        clip = clips_by_id.get(clip_id)
        if clip is None or not clip.path.is_file():
            continue
        media[clip_id] = probe_media(clip.path)
    return media


def storyboard_segments_debug_payload(
    storyboard: Storyboard,
    clip_media: dict[str, MediaInfo],
) -> dict[str, object]:
    """Build per-slot segment debug rows for UI / API inspection."""
    from viral_editor.audio.storyboard import storyboard_to_segments

    segments, roles, slot_ids = storyboard_to_segments(storyboard, clip_media)
    unified = hook_unified_crop_range(storyboard)
    hook_budget = hook_output_budget_s(storyboard)
    unified_label_speed: float | None = None
    if unified is not None and hook_budget > 1e-9:
        u0, u1 = unified
        unified_label_speed = round((u1 - u0) / hook_budget, 6)

    slots_by_id = {slot.id: slot for slot in storyboard.slots}
    rows: list[dict[str, object]] = []
    for slot_id, segment, role in zip(slot_ids, segments, roles):
        slot = slots_by_id[slot_id]
        src_span = round(segment.src_end_s - segment.src_start_s, 6)
        if _is_hook_family_role(role):
            label_speed = unified_label_speed
        else:
            label_speed = (
                round(src_span / slot.target_duration_s, 6)
                if slot.target_duration_s > 1e-9
                else None
            )
        rows.append(
            {
                "id": slot_id,
                "role": role,
                "target_duration_s": round(slot.target_duration_s, 6),
                "src_start_s": round(segment.src_start_s, 6),
                "src_end_s": round(segment.src_end_s, 6),
                "src_span_s": src_span,
                "speed_factor": round(segment.speed_factor, 6),
                "unified_label_speed": label_speed,
            }
        )

    summary: dict[str, object] = {
        "unified_crop": [round(unified[0], 6), round(unified[1], 6)] if unified else None,
        "hook_budget_s": round(hook_budget, 6),
        "hook_speed_s": unified_label_speed,
    }
    return {"slots": rows, "summary": summary}


def sync_config_clips_from_storyboard(
    config: JobConfig,
    storyboard: Storyboard,
) -> JobConfig:
    """Ensure config.clips contains every assigned clip id."""
    existing = {clip.id: clip for clip in config.clips}
    unified_hook_crop = hook_unified_crop_range(storyboard)
    for slot in storyboard.slots:
        if slot.assigned_clip_id is None:
            continue
        clip = existing.get(slot.assigned_clip_id)
        if clip is None:
            continue
        crop_start_s = slot.crop_start_s
        crop_end_s = slot.crop_end_s
        if (
            unified_hook_crop is not None
            and _is_hook_family_role(slot.role)
        ):
            crop_start_s, crop_end_s = unified_hook_crop
        existing[slot.assigned_clip_id] = clip.model_copy(
            update={
                "crop_start_s": crop_start_s,
                "crop_end_s": crop_end_s,
                "rotation_deg": slot.rotation_deg,
                "fit_mode": slot.fit_mode,
                "spatial_crop": slot.spatial_crop,
            }
        )
    return config.model_copy(update={"clips": sorted(existing.values(), key=lambda c: c.order)})
