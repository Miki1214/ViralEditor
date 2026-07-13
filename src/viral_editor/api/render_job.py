"""Final render orchestration for API jobs."""

from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path

from viral_editor.api.effects import hook_teaser_for_storyboard, spatial_fx_for_preview
from viral_editor.api.store import JobStore, write_job_config
from viral_editor.audio.captions import build_caption_chunks_for_slots
from viral_editor.audio.storyboard import (
    remap_fx_events_for_composite,
    storyboard_slots_complete,
    storyboard_to_segments,
)
from viral_editor.config import JobConfig
from viral_editor.models import RenderPlan, Storyboard
from viral_editor.pipeline_events import PipelineEvent
from viral_editor.utils.ffmpeg import FFmpegError, ensure_ffmpeg
from viral_editor.utils.logging import get_logger
from viral_editor.video.filter_builders import storyboard_mux_duration_s
from viral_editor.video.final_render import render_final

from viral_editor.api.storyboard import clip_media_for_storyboard, load_storyboard

logger = get_logger(__name__)


def _segment_transform_for_slot(slot) -> tuple[int, str, tuple[float, float, float, float] | None]:
    spatial = None
    if slot.spatial_crop is not None:
        spatial = (
            slot.spatial_crop.x,
            slot.spatial_crop.y,
            slot.spatial_crop.w,
            slot.spatial_crop.h,
        )
    return (slot.rotation_deg, slot.fit_mode, spatial)


def build_render_plan(
    config: JobConfig,
    storyboard: Storyboard,
    *,
    temp_dir: Path,
) -> tuple[RenderPlan, list[str], list[tuple[int, str, tuple[float, float, float, float] | None]], list[str]]:
    """Build a ``RenderPlan`` and assembly metadata from a filled storyboard."""
    clip_media = clip_media_for_storyboard(config, storyboard)
    segments, segment_roles, segment_slot_ids = storyboard_to_segments(storyboard, clip_media)
    if not segments:
        raise ValueError("No storyboard segments to render")

    slots_by_id = {slot.id: slot for slot in storyboard.slots}
    ordered_slots = [slots_by_id[slot_id] for slot_id in segment_slot_ids]
    transitions = [slot.transition_in for slot in ordered_slots]
    segment_transforms = [_segment_transform_for_slot(slot) for slot in ordered_slots]

    primary_media = next(iter(clip_media.values()), None)
    fx_events = (
        spatial_fx_for_preview(
            config,
            temp_dir,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
            media=primary_media,
            storyboard=storyboard,
        )
        if primary_media is not None
        else []
    )
    fx_events = remap_fx_events_for_composite(fx_events, storyboard)
    teaser_spec, _ = hook_teaser_for_storyboard(config, storyboard, clip_media)

    output_duration_s = storyboard_mux_duration_s(segments)
    plan = RenderPlan(
        output_duration_s=output_duration_s,
        speed_segments=segments,
        teaser=teaser_spec,
        fx_events=fx_events,
        title=None,
    )
    return plan, transitions, segment_transforms, segment_roles


def render_storyboard_final(
    config: JobConfig,
    storyboard: Storyboard,
    *,
    temp_dir: Path,
    out_path: Path,
    on_progress: Callable[[float], None] | None = None,
) -> float:
    """Encode the final MP4 for a storyboard with all slots assigned."""
    plan, transitions, segment_transforms, segment_roles = build_render_plan(
        config,
        storyboard,
        temp_dir=temp_dir,
    )

    needed_clip_ids = {segment.source_id for segment in plan.speed_segments if segment.source_id}
    clips_by_id = {clip.id: clip for clip in config.clips}
    clip_paths = {
        clip_id: clips_by_id[clip_id].path
        for clip_id in needed_clip_ids
        if clip_id in clips_by_id and clips_by_id[clip_id].path.is_file()
    }
    missing = needed_clip_ids - set(clip_paths)
    if missing:
        raise ValueError(f"Missing clip files for render: {', '.join(sorted(missing))}")

    clip_media = clip_media_for_storyboard(config, storyboard)
    clip_durations = {clip_id: info.duration_s for clip_id, info in clip_media.items()}

    _, segment_roles, segment_slot_ids = storyboard_to_segments(storyboard, clip_media)
    slots_by_id = {slot.id: slot for slot in storyboard.slots}
    ordered_slots = [slots_by_id[slot_id] for slot_id in segment_slot_ids]
    caption_chunks = build_caption_chunks_for_slots(
        config.caption,
        ordered_slots,
        emphasis_words=config.hook.emphasis_words,
    )
    slot_offsets = {slot.id: slot.out_start_s for slot in ordered_slots}

    render_final(
        plan,
        config.render,
        clip_paths=clip_paths,
        clip_durations=clip_durations,
        audio_path=config.audio_path,
        out_path=out_path,
        music_start_s=config.music.start_s,
        music_end_s=config.music.end_s,
        transitions=transitions,
        segment_transforms=segment_transforms,
        hook_text=config.hook.text,
        hook_style=config.hook_style,
        hook_emphasis_words=config.hook.emphasis_words,
        caption_chunks_by_slot=caption_chunks,
        caption_style=config.caption.style,
        slot_ids=segment_slot_ids,
        slot_offsets=slot_offsets,
        segment_roles=segment_roles,
        hook_start_mask=(
            config.teaser.mask
            if config.teaser.enabled and config.teaser.mask != "none"
            else None
        ),
        temp_dir=temp_dir,
        on_progress=on_progress,
    )
    return plan.output_duration_s


def start_final_render(store: JobStore, job_id: str) -> None:
    """Render the final MP4 on a background thread."""

    def _run() -> None:
        job = store.get(job_id)
        if job is None:
            return

        temp_dir = job.workspace / "temp"
        storyboard = load_storyboard(temp_dir)
        if storyboard is None:
            store.set_error(job_id, "Storyboard not found")
            store.publish(
                job_id,
                PipelineEvent.now("render", "error", message="Storyboard not found"),
            )
            return
        if not storyboard_slots_complete(storyboard):
            store.set_error(job_id, "Assign clips to all storyboard slots before rendering")
            store.publish(
                job_id,
                PipelineEvent.now(
                    "render",
                    "error",
                    message="Assign clips to all storyboard slots before rendering",
                ),
            )
            return

        store.set_status(job_id, "running")
        store.publish(job_id, PipelineEvent.now("render", "start"))
        store.publish(job_id, PipelineEvent.now("render", "info", message="progress:0.0"))

        last_progress_pct = -1.0

        def publish_encode_progress(pct: float) -> None:
            nonlocal last_progress_pct
            rounded = int(pct)
            if rounded <= last_progress_pct and pct < 100.0:
                return
            last_progress_pct = rounded
            store.publish(
                job_id,
                PipelineEvent.now("render", "info", message=f"progress:{pct:.1f}"),
            )

        try:
            ensure_ffmpeg()
            write_job_config(job.config, job.workspace)
            output_duration_s = render_storyboard_final(
                job.config,
                storyboard,
                temp_dir=temp_dir,
                out_path=job.config.output_path,
                on_progress=publish_encode_progress,
            )
        except (EnvironmentError, FFmpegError, RuntimeError, ValueError) as exc:
            logger.error("Job %s final render failed: %s", job_id, exc)
            store.set_error(job_id, str(exc))
            store.publish(job_id, PipelineEvent.now("render", "error", message=str(exc)))
            store.publish(job_id, PipelineEvent.now("pipeline", "error", message=str(exc)))
            return

        store.publish(job_id, PipelineEvent.now("render", "complete"))
        store.publish(job_id, PipelineEvent.now("pipeline", "complete"))
        store.complete(
            job_id,
            output_duration_s=output_duration_s,
            artifacts=list(job.artifacts),
            config=job.config,
            status="completed",
        )

    thread = threading.Thread(target=_run, name=f"render-{job_id[:8]}", daemon=True)
    thread.start()
