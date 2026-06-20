"""Retention FX helpers for composited preview."""

from __future__ import annotations

from pathlib import Path

from viral_editor.api.music import load_audio_timeline, load_beat_features, load_scope_lanes
from viral_editor.config import JobConfig
from viral_editor.models import AudioTimeline, ClipInput, FxEvent, MediaInfo, Storyboard, TeaserSpec, Transient
from viral_editor.video.spatial_fx import plan_spatial_fx
from viral_editor.video.teaser import build_teaser_spec


def _timeline_for_music_window(
    timeline: AudioTimeline,
    *,
    music_start_s: float,
    music_end_s: float,
) -> AudioTimeline:
    start_ms = int(round(music_start_s * 1000))
    end_ms = int(round(music_end_s * 1000))
    shifted: list[Transient] = []
    for transient in timeline.transients:
        if transient.timestamp_ms < start_ms or transient.timestamp_ms >= end_ms:
            continue
        shifted.append(
            transient.model_copy(
                update={"timestamp_ms": transient.timestamp_ms - start_ms},
            )
        )
    return timeline.model_copy(
        update={
            "transients": shifted,
            "audio_duration_seconds": max(music_end_s - music_start_s, 0.0),
        }
    )


def hook_teaser_for_storyboard(
    config: JobConfig,
    storyboard: Storyboard,
    clip_media: dict[str, MediaInfo],
) -> tuple[TeaserSpec | None, str | None]:
    """Build teaser spec from the hook slot when enabled."""
    if not config.teaser.enabled:
        return None, None
    hook_slot = next(
        (
            slot
            for slot in storyboard.slots
            if slot.role == "hook" and slot.assigned_clip_id is not None
        ),
        None,
    )
    if hook_slot is None or hook_slot.assigned_clip_id is None:
        return None, None
    clip = next(
        (item for item in config.clips if item.id == hook_slot.assigned_clip_id),
        None,
    )
    if clip is None:
        return None, None
    media = clip_media.get(clip.id)
    if media is None:
        return None, None
    hook_clip = ClipInput(
        id=clip.id,
        path=clip.path,
        order=clip.order,
        role=clip.role,
        crop_start_s=hook_slot.crop_start_s,
        crop_end_s=hook_slot.crop_end_s,
    )
    spec = build_teaser_spec(
        media,
        config.teaser,
        hook_clip=hook_clip,
        hook_media=media,
    )
    return spec, hook_slot.assigned_clip_id


def spatial_fx_for_preview(
    config: JobConfig,
    temp_dir: Path,
    *,
    music_start_s: float,
    music_end_s: float,
    media: MediaInfo,
) -> list[FxEvent]:
    if not config.spatial_fx.enabled:
        return []
    try:
        timeline = load_audio_timeline(temp_dir)
    except FileNotFoundError:
        return []
    windowed = _timeline_for_music_window(
        timeline,
        music_start_s=music_start_s,
        music_end_s=music_end_s,
    )
    features = load_beat_features(temp_dir)
    scope_lanes = load_scope_lanes(temp_dir)
    downbeats = (
        features.downbeat_times_s.tolist()
        if features is not None
        else []
    )
    return plan_spatial_fx(
        windowed,
        media,
        seed=config.seed,
        max_events_per_second=config.spatial_fx.max_events_per_second,
        scope_lanes=scope_lanes,
        downbeats=downbeats,
        window_start_s=music_start_s,
        window_end_s=music_end_s,
        retention=config.retention,
    )


def apply_effects_patch(config: JobConfig, payload) -> JobConfig:
    """Merge partial teaser / spatial FX / retention settings from an API patch."""
    updates: dict[str, object] = {}
    if payload.teaser is not None:
        teaser_patch = payload.teaser.model_dump(exclude_unset=True)
        if teaser_patch:
            updates["teaser"] = config.teaser.model_copy(update=teaser_patch)
    if payload.spatial_fx is not None:
        fx_patch = payload.spatial_fx.model_dump(exclude_unset=True)
        if fx_patch:
            updates["spatial_fx"] = config.spatial_fx.model_copy(update=fx_patch)
    if getattr(payload, "retention", None) is not None:
        retention_patch = payload.retention.model_dump(exclude_unset=True)
        if retention_patch:
            updates["retention"] = config.retention.model_copy(update=retention_patch)
    if not updates:
        return config
    return config.model_copy(update=updates)
