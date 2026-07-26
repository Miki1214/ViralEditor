"""Final-resolution render orchestrator (Phase 6)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from viral_editor.audio.preview import ensure_loop_seam_audio
from viral_editor.config import RenderConfig
from viral_editor.models import CaptionChunk, CaptionStyle, RenderPlan, TitleSpec
from viral_editor.utils.ffmpeg import FFmpegError, escape_filter_path, run_ffmpeg_with_progress, run_ffprobe_json
from viral_editor.video.filter_builders import (
    build_composite_filtergraph,
    composite_output_duration_s,
    storyboard_mux_duration_s,
)


def plan_output_duration_s(
    plan: RenderPlan,
    *,
    transitions: list[str] | None = None,
    xfade_s: float = 0.25,
) -> float:
    """Estimate mux duration for a render plan (teaser + body)."""
    body = storyboard_mux_duration_s(plan.speed_segments)
    teaser_s = plan.teaser.out_duration_s if plan.teaser is not None else 0.0
    return teaser_s + body


def verify_final_output(
    path: Path,
    render_cfg: RenderConfig,
    *,
    expected_duration_s: float,
    duration_tolerance_s: float | None = None,
) -> None:
    """Raise ValueError when the encoded file does not match the locked spec."""
    tolerance = duration_tolerance_s
    if tolerance is None:
        tolerance = 1.0 / max(render_cfg.fps, 1)
    if not path.is_file():
        raise ValueError(f"render output missing: {path}")

    format_payload = run_ffprobe_json(
        ["-show_entries", "format=duration", "-show_streams", str(path)]
    )
    streams = format_payload.get("streams", [])
    video = next((stream for stream in streams if stream.get("codec_type") == "video"), None)
    audio = next((stream for stream in streams if stream.get("codec_type") == "audio"), None)
    if video is None or audio is None:
        raise ValueError("render output must contain video and audio streams")

    width = int(video.get("width", 0))
    height = int(video.get("height", 0))
    if width != render_cfg.width or height != render_cfg.height:
        raise ValueError(
            f"render resolution {width}x{height} != {render_cfg.width}x{render_cfg.height}"
        )

    vcodec = str(video.get("codec_name", ""))
    if render_cfg.vcodec == "libx264" and vcodec != "h264":
        raise ValueError(f"unexpected video codec {vcodec!r}")

    acodec = str(audio.get("codec_name", ""))
    if render_cfg.acodec == "aac" and acodec not in ("aac", "mp4a"):
        raise ValueError(f"unexpected audio codec {acodec!r}")

    fps_text = str(video.get("avg_frame_rate", "0/1"))
    if "/" in fps_text:
        num, den = fps_text.split("/", 1)
        fps = float(num) / max(float(den), 1.0)
    else:
        fps = float(fps_text)
    if abs(fps - float(render_cfg.fps)) > 1.0:
        raise ValueError(f"render fps {fps:.3f} != {render_cfg.fps}")

    probed_duration = float(format_payload["format"]["duration"])
    if abs(probed_duration - expected_duration_s) > tolerance:
        raise ValueError(
            f"render duration {probed_duration:.3f}s != {expected_duration_s:.3f}s"
        )


def _append_looped_music_input(
    command: list[str],
    *,
    audio_path: Path,
    music_start_s: float,
    music_end_s: float,
    temp_dir: Path,
) -> None:
    loop_wav = ensure_loop_seam_audio(
        audio_path,
        start_s=music_start_s,
        end_s=music_end_s,
        temp_dir=temp_dir,
    )
    command.extend(["-stream_loop", "-1", "-i", str(loop_wav)])


def build_final_encode_args(
    render_cfg: RenderConfig,
    *,
    audio_input_index: int,
    duration_s: float | None = None,
) -> list[str]:
    """Return ffmpeg output encode/mux flags for the final render."""
    args = [
        "-map",
        "[outv]",
        "-map",
        f"{audio_input_index}:a:0",
        "-c:v",
        render_cfg.vcodec,
        "-preset",
        render_cfg.preset,
        "-crf",
        str(render_cfg.crf),
        "-pix_fmt",
        render_cfg.pix_fmt,
        "-r",
        str(render_cfg.fps),
        "-vsync",
        "cfr",
        "-c:a",
        render_cfg.acodec,
        "-b:a",
        "192k",
        "-movflags",
        "+faststart",
    ]
    if duration_s is not None:
        args.extend(["-t", f"{duration_s:.6f}"])
    return args


def build_final_filtergraph(
    plan: RenderPlan,
    render_cfg: RenderConfig,
    *,
    clip_input_index: dict[str, int] | None = None,
    clip_durations: dict[str, float] | None = None,
    clip_transforms: dict[str, tuple[int, str, tuple[float, float, float, float] | None]] | None = None,
    segment_transforms: list[tuple[int, str, tuple[float, float, float, float] | None]] | None = None,
    transitions: list[str] | None = None,
    hook_text: str | None = None,
    hook_style: CaptionStyle | None = None,
    hook_emphasis_words: list[str] | None = None,
    caption_chunks_by_slot: dict[str, list[CaptionChunk]] | None = None,
    caption_style: CaptionStyle | None = None,
    slot_ids: list[str] | None = None,
    slot_offsets: dict[str, float] | None = None,
    segment_roles: list[str] | None = None,
    hook_start_mask: str | None = None,
    title: TitleSpec | None = None,
    title_ass_path: Path | None = None,
) -> str:
    """Build a full-resolution filtergraph for the aggregate render plan."""
    scale = (render_cfg.width, render_cfg.height)
    transition_list = transitions or ["cut"] * len(plan.speed_segments)
    ass_path: str | None = None
    if title_ass_path is not None:
        ass_path = escape_filter_path(title_ass_path)

    graph = build_composite_filtergraph(
        plan.speed_segments,
        transition_list,
        scale=scale,
        clip_input_index=clip_input_index,
        clip_durations=clip_durations,
        clip_transforms=clip_transforms,
        segment_transforms=segment_transforms,
        hook_text=hook_text,
        hook_style=hook_style,
        hook_emphasis_words=hook_emphasis_words,
        caption_chunks_by_slot=caption_chunks_by_slot,
        caption_style=caption_style,
        slot_ids=slot_ids,
        slot_offsets=slot_offsets,
        segment_roles=segment_roles,
        hook_start_mask=hook_start_mask,
        fx_events=plan.fx_events,
        fps=float(render_cfg.fps),
        rotate_gain=1.0,
        pan_gain=1.0,
    )
    if ass_path and title is not None:
        graph = graph.replace("copy[outv]", f"copy[bodyfx];[bodyfx]ass={ass_path}[outv]", 1)
    del title
    return graph


def render_final(
    plan: RenderPlan,
    render_cfg: RenderConfig,
    *,
    clip_paths: dict[str, Path],
    clip_durations: dict[str, float],
    audio_path: Path,
    out_path: Path,
    music_start_s: float | None = None,
    music_end_s: float | None = None,
    transitions: list[str] | None = None,
    clip_transforms: dict[str, tuple[int, str, tuple[float, float, float, float] | None]] | None = None,
    segment_transforms: list[tuple[int, str, tuple[float, float, float, float] | None]] | None = None,
    hook_text: str | None = None,
    hook_style: CaptionStyle | None = None,
    hook_emphasis_words: list[str] | None = None,
    caption_chunks_by_slot: dict[str, list[CaptionChunk]] | None = None,
    caption_style: CaptionStyle | None = None,
    slot_ids: list[str] | None = None,
    slot_offsets: dict[str, float] | None = None,
    segment_roles: list[str] | None = None,
    hook_start_mask: str | None = None,
    title: TitleSpec | None = None,
    title_ass_path: Path | None = None,
    temp_dir: Path | None = None,
    verify: bool = True,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    """Render the final locked-spec MP4 for a render plan."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    work_temp = temp_dir or out_path.parent

    clip_input_index: dict[str, int] = {}
    video_inputs: list[Path] = []
    for clip_id, path in sorted(clip_paths.items(), key=lambda item: item[0]):
        clip_input_index[clip_id] = len(video_inputs)
        video_inputs.append(path)

    filtergraph = build_final_filtergraph(
        plan,
        render_cfg,
        clip_input_index=clip_input_index,
        clip_durations=clip_durations,
        clip_transforms=clip_transforms,
        segment_transforms=segment_transforms,
        transitions=transitions,
        hook_text=hook_text,
        hook_style=hook_style,
        hook_emphasis_words=hook_emphasis_words,
        caption_chunks_by_slot=caption_chunks_by_slot,
        caption_style=caption_style,
        slot_ids=slot_ids,
        slot_offsets=slot_offsets,
        segment_roles=segment_roles,
        hook_start_mask=hook_start_mask,
        title=title,
        title_ass_path=title_ass_path,
    )

    total_duration_s = plan_output_duration_s(plan, transitions=transitions)

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

    command.extend(["-filter_complex", filtergraph])
    command.extend(
        build_final_encode_args(
            render_cfg,
            audio_input_index=audio_input_index,
            duration_s=total_duration_s,
        )
    )
    command.append(str(out_path))

    try:
        run_ffmpeg_with_progress(
            command,
            duration_s=total_duration_s,
            on_progress=on_progress,
        )
    except FFmpegError as exc:
        detail = str(exc)
        if exc.stderr:
            detail = f"{detail}\n{exc.stderr}"
        raise RuntimeError(f"Final render failed: {detail}") from exc

    if verify:
        verify_final_output(
            out_path,
            render_cfg,
            expected_duration_s=total_duration_s,
        )
    return out_path
