"""Clip reel artifacts and refresh helpers."""

from __future__ import annotations

from pathlib import Path

from viral_editor.config import JobConfig
from viral_editor.ingest.loader import probe_media
from viral_editor.models import ClipInput, ClipReel, MediaInfo, write_artifact
from viral_editor.video.clip_reel import build_reel, clip_paths_by_id
from viral_editor.video.teaser import build_teaser_spec, teaser_body_output_duration


def load_clip_reel(temp_dir: Path) -> ClipReel | None:
    path = temp_dir / "clip_reel.json"
    if not path.is_file():
        return None
    return ClipReel.model_validate_json(path.read_text(encoding="utf-8"))


def probe_clip_media(config: JobConfig) -> dict[str, MediaInfo]:
    """Probe every included clip path on the job config."""
    media: dict[str, MediaInfo] = {}
    for clip in config.effective_clips():
        media[clip.id] = probe_media(clip.path)
    return media


def primary_video_media(config: JobConfig, clip_media: dict[str, MediaInfo]) -> MediaInfo:
    clips = config.effective_clips()
    if clips and clips[0].id in clip_media:
        return clip_media[clips[0].id]
    if config.video_path is not None:
        return probe_media(config.video_path)
    raise ValueError("No video source available for speed planning")


def build_reel_for_config(
    config: JobConfig,
    *,
    clip_media: dict[str, MediaInfo],
    music_window_duration_s: float,
) -> ClipReel:
    """Build the virtual reel for the current clip selection and music window."""
    _, reel, _, _ = speed_planning_context(
        config,
        clip_media,
        music_window_duration_s,
    )
    return reel


def speed_planning_context(
    config: JobConfig,
    clip_media: dict[str, MediaInfo],
    music_window_duration_s: float,
) -> tuple[MediaInfo, ClipReel, float, object]:
    """Return primary video, reel, body output duration, and teaser spec."""
    effective = config.effective_clips()
    hook = next((clip for clip in effective if clip.role == "hook"), None)
    hook_media = clip_media.get(hook.id) if hook is not None else None
    video = primary_video_media(config, clip_media)
    teaser_spec = build_teaser_spec(
        video,
        config.teaser,
        hook_clip=hook,
        hook_media=hook_media,
    )
    body_output_duration_s = teaser_body_output_duration(
        music_window_duration_s,
        teaser_spec,
    )
    source_clips = config.clips if config.clips else effective
    included = [clip for clip in source_clips if clip.included]
    reel = build_reel(
        included,
        clip_media,
        body_output_duration_s=body_output_duration_s,
        speed_config=config.speed_ramp,
    )
    return video, reel, body_output_duration_s, teaser_spec


def clip_info_payload(
    config: JobConfig,
    clip_media: dict[str, MediaInfo],
    reel: ClipReel | None = None,
) -> list[dict]:
    """Serialize per-clip metadata for the API."""
    payload: list[dict] = []
    for clip in sorted(config.clips, key=lambda item: item.order):
        media = clip_media.get(clip.id)
        if media is None:
            continue
        crop_start = clip.crop_start_s if clip.crop_start_s is not None else 0.0
        crop_end = clip.crop_end_s if clip.crop_end_s is not None else media.duration_s
        payload.append(
            {
                "id": clip.id,
                "filename": clip.path.name,
                "order": clip.order,
                "included": clip.included,
                "role": clip.role,
                "crop_start_s": clip.crop_start_s,
                "crop_end_s": clip.crop_end_s,
                "duration_s": media.duration_s,
                "crop_duration_s": max(0.0, crop_end - crop_start),
                "width": media.width,
                "height": media.height,
                "fps": media.fps,
            }
        )
    return payload


def persist_clip_reel(config: JobConfig, temp_dir: Path, reel: ClipReel) -> None:
    write_artifact(reel, "clip_reel", temp_dir)


def clip_durations_map(clip_media: dict[str, MediaInfo]) -> dict[str, float]:
    return {clip_id: info.duration_s for clip_id, info in clip_media.items()}


def used_clip_paths(config: JobConfig, plan_segments_source_ids: set[str | None]) -> dict[str, Path]:
    paths = clip_paths_by_id(config.effective_clips())
    if not plan_segments_source_ids:
        return paths
    return {
        clip_id: path
        for clip_id, path in paths.items()
        if clip_id in plan_segments_source_ids
    }


def apply_clip_updates(
    config: JobConfig,
    updates: list[ClipInput],
) -> JobConfig:
    """Merge clip PATCH payloads into the job config."""
    by_id = {clip.id: clip for clip in config.clips}
    for update in updates:
        existing = by_id.get(update.id)
        if existing is None:
            continue
        by_id[update.id] = existing.model_copy(
            update={
                "order": update.order,
                "included": update.included,
                "role": update.role,
                "crop_start_s": update.crop_start_s,
                "crop_end_s": update.crop_end_s,
            }
        )
    return config.model_copy(update={"clips": sorted(by_id.values(), key=lambda clip: clip.order)})


def refresh_clips_selection(
    config: JobConfig,
    temp_dir: Path,
    updates: list[ClipInput],
) -> tuple[JobConfig, ClipReel, object]:
    """Apply clip edits and recompute reel + speed artifacts."""
    from viral_editor.api.speed import compute_speed_options, invalidate_speed_previews
    from viral_editor.models import write_artifact

    updated = apply_clip_updates(config, updates)
    invalidate_speed_previews(temp_dir)
    option_set = compute_speed_options(updated, temp_dir)
    write_artifact(option_set, "speed_ramp_options", temp_dir)
    selected_plan = next(
        (option.plan for option in option_set.options if option.style == option_set.selected_style),
        option_set.options[0].plan,
    )
    write_artifact(selected_plan, "speed_segments", temp_dir)
    reel = load_clip_reel(temp_dir)
    if reel is None:
        clip_media = probe_clip_media(updated)
        if updated.music.start_s is not None and updated.music.end_s is not None:
            music_window_s = updated.music.end_s - updated.music.start_s
        else:
            from viral_editor.api.music import load_audio_timeline

            timeline = load_audio_timeline(temp_dir)
            music_window_s = timeline.audio_duration_seconds
        reel = build_reel_for_config(
            updated,
            clip_media=clip_media,
            music_window_duration_s=music_window_s,
        )
    return updated, reel, option_set
