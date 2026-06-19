"""Load speed-ramp artifacts and refresh style selection."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from viral_editor.audio.block_planner import trim_timeline_to_window
from viral_editor.config import JobConfig, SpeedRampConfig
from viral_editor.models import (
    MusicSection,
    SpeedRampOptionSet,
    SpeedRampPlan,
    write_artifact,
)
from viral_editor.api.clips import (
    clip_durations_map,
    persist_clip_reel,
    probe_clip_media,
    speed_planning_context,
)
from viral_editor.api.music import (
    load_audio_timeline,
    load_beat_features,
    load_music_structure,
    load_onset_envelope,
)
from viral_editor.video.speed_ramp import (
    plan_speed_options,
    trim_beat_features_to_window,
    trim_envelope_to_window,
)


def load_speed_ramp_options(temp_dir: Path) -> SpeedRampOptionSet | None:
    path = temp_dir / "speed_ramp_options.json"
    if not path.is_file():
        return None
    return SpeedRampOptionSet.model_validate_json(path.read_text(encoding="utf-8"))


def load_speed_segments(temp_dir: Path) -> SpeedRampPlan | None:
    path = temp_dir / "speed_segments.json"
    if not path.is_file():
        return None
    return SpeedRampPlan.model_validate_json(path.read_text(encoding="utf-8"))


def _trim_sections(
    sections: list[MusicSection],
    *,
    start_s: float,
    end_s: float,
) -> list[MusicSection]:
    duration = end_s - start_s
    trimmed: list[MusicSection] = []
    for section in sections:
        if section.end_s <= start_s or section.start_s >= end_s:
            continue
        trimmed.append(
            section.model_copy(
                update={
                    "start_s": max(0.0, section.start_s - start_s),
                    "end_s": min(duration, section.end_s - start_s),
                }
            )
        )
    return trimmed


def compute_speed_options(
    config: JobConfig,
    temp_dir: Path,
    *,
    resolve_overrides: dict[str, float | int | str | None] | None = None,
) -> SpeedRampOptionSet:
    """Recompute all speed options from analysis artifacts."""
    timeline = load_audio_timeline(temp_dir)
    envelope = load_onset_envelope(temp_dir)
    features = load_beat_features(temp_dir)
    structure = load_music_structure(temp_dir)
    sections = structure.sections if structure is not None else []

    if config.music.start_s is not None and config.music.end_s is not None:
        output_duration_s = config.music.end_s - config.music.start_s
        ramp_timeline = trim_timeline_to_window(
            timeline,
            start_s=config.music.start_s,
            end_s=config.music.end_s,
        )
        ramp_envelope = trim_envelope_to_window(
            envelope,
            start_s=config.music.start_s,
            end_s=config.music.end_s,
        )
        ramp_features = (
            trim_beat_features_to_window(
                features,
                start_s=config.music.start_s,
                end_s=config.music.end_s,
            )
            if features is not None
            else None
        )
        ramp_sections = _trim_sections(
            sections,
            start_s=config.music.start_s,
            end_s=config.music.end_s,
        )
    else:
        output_duration_s = timeline.audio_duration_seconds
        ramp_timeline = timeline
        ramp_envelope = envelope
        ramp_features = features
        ramp_sections = sections

    clip_media = probe_clip_media(config)
    video, reel, body_output_duration_s, _teaser = speed_planning_context(
        config,
        clip_media,
        output_duration_s,
    )
    persist_clip_reel(config, temp_dir, reel)

    return plan_speed_options(
        ramp_timeline,
        ramp_envelope,
        video,
        output_duration_s=body_output_duration_s,
        base_config=config.speed_ramp,
        features=ramp_features,
        sections=ramp_sections,
        sr=timeline.sample_rate,
        output_fps=float(config.render.fps),
        resolve_overrides=resolve_overrides,
        reel=reel,
    )


def invalidate_speed_previews(temp_dir: Path) -> None:
    preview_dir = temp_dir / "previews"
    if not preview_dir.is_dir():
        return
    for path in preview_dir.glob("speed_*.mp4"):
        path.unlink(missing_ok=True)


def refresh_speed_selection(
    config: JobConfig,
    temp_dir: Path,
    *,
    style: str | None = None,
    overrides: dict[str, float | int | str | None] | None = None,
) -> tuple[JobConfig, SpeedRampOptionSet]:
    """Apply style/overrides, recompute options, and persist selected segments."""
    speed_ramp = config.speed_ramp.model_copy(deep=True)
    if style is not None:
        speed_ramp = speed_ramp.model_copy(update={"style": style})
    if overrides:
        allowed = {
            key: value
            for key, value in overrides.items()
            if key in SpeedRampConfig.model_fields and value is not None
        }
        if allowed:
            speed_ramp = speed_ramp.model_copy(update=allowed)

    updated_config = config.model_copy(update={"speed_ramp": speed_ramp})
    invalidate_speed_previews(temp_dir)
    option_set = compute_speed_options(
        updated_config,
        temp_dir,
        resolve_overrides=overrides,
    )
    write_artifact(option_set, "speed_ramp_options", temp_dir)

    selected_plan = next(
        (option.plan for option in option_set.options if option.style == option_set.selected_style),
        option_set.options[0].plan,
    )
    write_artifact(selected_plan, "speed_segments", temp_dir)
    return updated_config, option_set


def speed_proxy_cache_key(
    *,
    style: str,
    plan: SpeedRampPlan,
    video_path: Path | None,
    clip_paths: dict[str, Path] | None,
    music_start_s: float | None,
    music_end_s: float | None,
) -> str:
    payload = {
        "style": style,
        "plan": plan.model_dump(mode="json"),
        "video": str(video_path.resolve()) if video_path is not None else None,
        "clips": (
            {clip_id: str(path.resolve()) for clip_id, path in sorted(clip_paths.items())}
            if clip_paths
            else None
        ),
        "music_start_s": music_start_s,
        "music_end_s": music_end_s,
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"speed_{style}_{digest}"
