"""Low-resolution speed-ramp proxy render for UI preview."""

from __future__ import annotations

from pathlib import Path

from viral_editor.audio.preview import ensure_loop_seam_audio
from viral_editor.models import CaptionChunk, CaptionStyle, SpeedRampPlan, SpeedSegment
from viral_editor.utils.ffmpeg import FFmpegError, resolve_drawtext_fontfile, run_ffmpeg
from viral_editor.video.filter_builders import (
    DEFAULT_COMPOSITE_FPS,
    DEFAULT_PAN_GAIN,
    DEFAULT_ROTATE_GAIN,
    build_composite_filtergraph,
    build_proxy_filtergraph,
    composite_output_duration_s,
)

COMPOSITE_FPS = DEFAULT_COMPOSITE_FPS
PREVIEW_ROTATE_GAIN = DEFAULT_ROTATE_GAIN
PREVIEW_PAN_GAIN = DEFAULT_PAN_GAIN


def _append_looped_music_input(
    command: list[str],
    *,
    audio_path: Path,
    music_start_s: float,
    music_end_s: float,
    temp_dir: Path,
) -> None:
    """Append a seamlessly looped music input (index = inputs already in command)."""
    loop_wav = ensure_loop_seam_audio(
        audio_path,
        start_s=music_start_s,
        end_s=music_end_s,
        temp_dir=temp_dir,
    )
    command.extend(["-stream_loop", "-1", "-i", str(loop_wav)])


def render_composite(
    audio_path: Path,
    segments: list[SpeedSegment],
    transitions: list[str],
    *,
    clip_paths: dict[str, Path],
    clip_durations: dict[str, float],
    clip_transforms: dict[str, tuple[int, str, tuple[float, float, float, float] | None]] | None = None,
    segment_transforms: list[tuple[int, str, tuple[float, float, float, float] | None]] | None = None,
    music_start_s: float | None,
    music_end_s: float | None,
    out_path: Path,
    hook_text: str | None = None,
    hook_style: CaptionStyle | None = None,
    caption_chunks_by_slot: dict[str, list[CaptionChunk]] | None = None,
    caption_style: CaptionStyle | None = None,
    slot_ids: list[str] | None = None,
    scale: tuple[int, int] = (360, 640),
    temp_dir: Path | None = None,
    segment_roles: list[str] | None = None,
    hook_start_mask: str | None = None,
    fx_events: list | None = None,
    fx_seed: int = 42,
    fx_intensity: float = 1.0,
) -> Path:
    """Render a storyboard composite preview with trimmed music mux."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work_temp = temp_dir or out_path.parent

    clip_input_index: dict[str, int] = {}
    video_inputs: list[Path] = []
    for clip_id, path in sorted(clip_paths.items(), key=lambda item: item[0]):
        clip_input_index[clip_id] = len(video_inputs)
        video_inputs.append(path)

    filtergraph = build_composite_filtergraph(
        segments,
        transitions,
        scale=scale,
        clip_input_index=clip_input_index,
        clip_durations=clip_durations,
        clip_transforms=clip_transforms,
        segment_transforms=segment_transforms,
        hook_text=hook_text,
        hook_style=hook_style,
        caption_chunks_by_slot=caption_chunks_by_slot,
        caption_style=caption_style,
        slot_ids=slot_ids,
        segment_roles=segment_roles,
        hook_start_mask=hook_start_mask,
        fx_events=fx_events,
        fx_seed=fx_seed,
        fx_intensity=fx_intensity,
        rotate_gain=PREVIEW_ROTATE_GAIN,
        pan_gain=PREVIEW_PAN_GAIN,
    )

    total_duration_s = composite_output_duration_s(
        segments,
        transitions=transitions,
    )

    command: list[str] = ["-y"]
    for path in video_inputs:
        command.extend(["-i", str(path)])

    has_music_window = (
        music_start_s is not None
        and music_end_s is not None
        and music_end_s > music_start_s
    )
    if has_music_window:
        audio_input_index = len(video_inputs)
        _append_looped_music_input(
            command,
            audio_path=audio_path,
            music_start_s=music_start_s,
            music_end_s=music_end_s,
            temp_dir=work_temp,
        )
    else:
        audio_input_index = len(video_inputs)
        command.extend(["-i", str(audio_path)])

    command.extend(
        [
            "-filter_complex",
            filtergraph,
            "-map",
            "[outv]",
            "-map",
            f"{audio_input_index}:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-t",
            f"{total_duration_s:.6f}",
            str(out_path),
        ]
    )
    try:
        run_ffmpeg(command)
    except FFmpegError as exc:
        detail = str(exc)
        if exc.stderr:
            detail = f"{detail}\n{exc.stderr}"
        raise RuntimeError(f"Composite preview render failed: {detail}") from exc
    return out_path


def render_speed_proxy(
    audio_path: Path,
    plan: SpeedRampPlan,
    *,
    video_path: Path | None = None,
    clip_paths: dict[str, Path] | None = None,
    clip_durations: dict[str, float] | None = None,
    music_start_s: float | None,
    music_end_s: float | None,
    out_path: Path,
    scale: tuple[int, int] = (360, 640),
    temp_dir: Path | None = None,
) -> Path:
    """Render a cached low-res proxy clip with trimmed music mux."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work_temp = temp_dir or out_path.parent

    clip_input_index: dict[str, int] = {}
    video_inputs: list[Path] = []
    if clip_paths:
        for clip_id, path in sorted(clip_paths.items(), key=lambda item: item[0]):
            clip_input_index[clip_id] = len(video_inputs)
            video_inputs.append(path)
    elif video_path is not None:
        video_inputs = [video_path]
    else:
        raise ValueError("Provide video_path or clip_paths for proxy render")

    filtergraph = build_proxy_filtergraph(
        plan,
        scale=scale,
        clip_input_index=clip_input_index or None,
        clip_durations=clip_durations,
    )

    command: list[str] = ["-y"]
    for path in video_inputs:
        command.extend(["-i", str(path)])

    has_music_window = (
        music_start_s is not None
        and music_end_s is not None
        and music_end_s > music_start_s
    )
    if has_music_window:
        audio_input_index = len(video_inputs)
        _append_looped_music_input(
            command,
            audio_path=audio_path,
            music_start_s=music_start_s,
            music_end_s=music_end_s,
            temp_dir=work_temp,
        )
    else:
        audio_input_index = len(video_inputs)
        command.extend(["-i", str(audio_path)])

    command.extend(
        [
            "-filter_complex",
            filtergraph,
            "-map",
            "[outv]",
            "-map",
            f"{audio_input_index}:a:0",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "28",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-shortest",
            str(out_path),
        ]
    )
    try:
        run_ffmpeg(command)
    except FFmpegError as exc:
        raise RuntimeError(f"Speed proxy render failed: {exc}") from exc
    return out_path


def selected_plan_segments(plan: SpeedRampPlan) -> list[SpeedSegment]:
    """Expose segments for tests and callers."""
    return plan.segments


__all__ = [
    "COMPOSITE_FPS",
    "PREVIEW_PAN_GAIN",
    "PREVIEW_ROTATE_GAIN",
    "build_composite_filtergraph",
    "build_proxy_filtergraph",
    "composite_output_duration_s",
    "render_composite",
    "render_speed_proxy",
    "resolve_drawtext_fontfile",
    "selected_plan_segments",
]
