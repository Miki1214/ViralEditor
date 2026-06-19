"""Low-resolution speed-ramp proxy render for UI preview (Phase 6 supersedes)."""

from __future__ import annotations

from pathlib import Path

from viral_editor.audio.preview import ensure_loop_seam_audio
from viral_editor.models import SpeedRampPlan, SpeedSegment
from viral_editor.utils.ffmpeg import FFmpegError, resolve_drawtext_fontfile, run_ffmpeg


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


def _source_trim_spans(
    src_start: float,
    src_end: float,
    src_duration: float,
    *,
    allow_wrap: bool,
) -> list[tuple[float, float]]:
    """Expand a possibly wrapped source range into in-bounds trim spans."""
    if src_end <= src_start + 1e-9:
        return []
    if src_duration <= 0:
        return [(src_start, src_end)]

    if not allow_wrap and src_end <= src_duration + 1e-6:
        return [(max(0.0, src_start), min(src_end, src_duration))]

    spans: list[tuple[float, float]] = []
    pos = src_start
    while pos < src_end - 1e-9:
        local = pos % src_duration
        remaining = src_end - pos
        to_cycle_end = src_duration - local if local > 1e-9 else src_duration
        chunk = min(remaining, to_cycle_end)
        if chunk <= 1e-9:
            chunk = min(remaining, src_duration)
        spans.append((local, local + chunk))
        pos += chunk
    return spans


def _visual_filters(
    width: int,
    height: int,
    *,
    rotation_deg: int = 0,
    fit_mode: str = "contain",
    spatial_crop: tuple[float, float, float, float] | None = None,
) -> str:
    """Rotate, optionally spatial-crop, then scale/pad to the output frame."""
    parts: list[str] = []
    rot = rotation_deg % 360
    if rot == 90:
        parts.append("transpose=1")
    elif rot == 180:
        parts.append("hflip,vflip")
    elif rot == 270:
        parts.append("transpose=2")
    if spatial_crop is not None:
        crop_x, crop_y, crop_w, crop_h = spatial_crop
        parts.append(
            f"crop=iw*{crop_w:.6f}:ih*{crop_h:.6f}:"
            f"iw*{crop_x:.6f}:ih*{crop_y:.6f}"
        )
        parts.append(f"scale={width}:{height},setsar=1")
    elif fit_mode == "cover":
        parts.append(
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},setsar=1"
        )
    else:
        parts.append(
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1"
        )
    return ",".join(parts)


def _segment_filter_chains(
    segment: SpeedSegment,
    *,
    input_label: str,
    src_duration: float,
    width: int,
    height: int,
    label_prefix: str,
    allow_wrap: bool,
    rotation_deg: int = 0,
    fit_mode: str = "contain",
    spatial_crop: tuple[float, float, float, float] | None = None,
) -> tuple[list[str], str]:
    """Build filter chains for one output segment, including source loops."""
    out_len = max(segment.out_end_s - segment.out_start_s, 1e-6)
    speed = max(segment.speed_factor, 1e-6)
    spans = _source_trim_spans(
        segment.src_start_s,
        segment.src_end_s,
        src_duration,
        allow_wrap=allow_wrap,
    )

    if not spans:
        spans = [(0.0, min(out_len * speed, max(src_duration, 1e-6)))]

    visual = _visual_filters(
        width,
        height,
        rotation_deg=rotation_deg,
        fit_mode=fit_mode,
        spatial_crop=spatial_crop,
    )

    if len(spans) == 1:
        start, end = spans[0]
        label = label_prefix
        chain = (
            f"[{input_label}]trim=start={start:.6f}:end={end:.6f},"
            f"setpts=PTS-STARTPTS,"
            f"setpts=PTS/{speed:.6f},"
            f"{visual},"
            f"trim=duration={out_len:.6f},setpts=PTS-STARTPTS[{label}]"
        )
        return [chain], f"[{label}]"

    parts: list[str] = []
    span_labels: list[str] = []
    total_src = max(segment.src_end_s - segment.src_start_s, 1e-6)

    for index, (start, end) in enumerate(spans):
        span_src = max(end - start, 1e-6)
        span_out = out_len * (span_src / total_src)
        span_labels.append(f"{label_prefix}s{index}")
        parts.append(
            f"[{input_label}]trim=start={start:.6f}:end={end:.6f},"
            f"setpts=PTS-STARTPTS,"
            f"setpts=PTS/{speed:.6f},"
            f"{visual},"
            f"trim=duration={span_out:.6f},setpts=PTS-STARTPTS[{span_labels[-1]}]"
        )

    joined = "".join(f"[{name}]" for name in span_labels)
    merged = f"{label_prefix}merged"
    parts.append(f"{joined}concat=n={len(span_labels)}:v=1:a=0[{merged}]")
    parts.append(
        f"[{merged}]trim=duration={out_len:.6f},setpts=PTS-STARTPTS[{label_prefix}]"
    )
    return parts, f"[{label_prefix}]"


def build_proxy_filtergraph(
    plan: SpeedRampPlan,
    *,
    scale: tuple[int, int] = (360, 640),
    clip_input_index: dict[str, int] | None = None,
    clip_durations: dict[str, float] | None = None,
) -> str:
    """Build an ffmpeg filtergraph for segment-wise speed preview."""
    if not plan.segments:
        return f"nullsrc=s={scale[0]}x{scale[1]}:d=0.1,format=yuv420p"

    width, height = scale
    parts: list[str] = []
    concat_inputs: list[str] = []

    for index, segment in enumerate(plan.segments):
        label = f"v{index}"
        input_idx = 0
        src_dur = plan.src_duration_s
        allow_wrap = segment.source_id is None
        if segment.source_id and clip_input_index is not None:
            input_idx = clip_input_index.get(segment.source_id, 0)
        if segment.source_id and clip_durations is not None:
            src_dur = clip_durations.get(segment.source_id, plan.src_duration_s)
            allow_wrap = False
        chains, concat_ref = _segment_filter_chains(
            segment,
            input_label=f"{input_idx}:v",
            src_duration=src_dur,
            width=width,
            height=height,
            label_prefix=label,
            allow_wrap=allow_wrap,
        )
        parts.extend(chains)
        concat_inputs.append(concat_ref)

    parts.append(f"{''.join(concat_inputs)}concat=n={len(plan.segments)}:v=1:a=0[outv]")
    return ";".join(parts)


def build_composite_filtergraph(
    segments: list[SpeedSegment],
    transitions: list[str],
    *,
    scale: tuple[int, int] = (360, 640),
    clip_input_index: dict[str, int] | None = None,
    clip_durations: dict[str, float] | None = None,
    clip_transforms: dict[str, tuple[int, str, tuple[float, float, float, float] | None]] | None = None,
    hook_text: str | None = None,
    xfade_s: float = 0.25,
) -> str:
    """Build ffmpeg filtergraph for storyboard slots with optional xfade + hook title."""
    if not segments:
        return f"nullsrc=s={scale[0]}x{scale[1]}:d=0.1,format=yuv420p"

    width, height = scale
    parts: list[str] = []
    segment_labels: list[str] = []

    for index, segment in enumerate(segments):
        label = f"slot{index}"
        input_idx = 0
        src_dur = segment.src_end_s - segment.src_start_s
        if segment.source_id and clip_input_index is not None:
            input_idx = clip_input_index.get(segment.source_id, 0)
        if segment.source_id and clip_durations is not None:
            src_dur = clip_durations.get(segment.source_id, src_dur)
        rotation_deg = 0
        fit_mode = "contain"
        spatial_crop = None
        if segment.source_id and clip_transforms is not None:
            rotation_deg, fit_mode, spatial_crop = clip_transforms.get(
                segment.source_id,
                (0, "contain", None),
            )
        chains, concat_ref = _segment_filter_chains(
            segment,
            input_label=f"{input_idx}:v",
            src_duration=max(src_dur, 1e-6),
            width=width,
            height=height,
            label_prefix=label,
            allow_wrap=False,
            rotation_deg=rotation_deg,
            fit_mode=fit_mode,
            spatial_crop=spatial_crop,
        )
        parts.extend(chains)
        if index == 0 and hook_text:
            font_path = resolve_drawtext_fontfile()
            if font_path:
                escaped = hook_text.replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")
                titled = f"{label}titled"
                parts.append(
                    f"{concat_ref}drawtext=text='{escaped}':fontfile='{font_path}':fontsize=28:fontcolor=white:"
                    f"x=(w-text_w)/2:y=h*0.12:box=1:boxcolor=black@0.55:boxborderw=8[{titled}]"
                )
                concat_ref = f"[{titled}]"
        segment_labels.append(concat_ref)

    if len(segment_labels) == 1:
        parts.append(f"{segment_labels[0]}copy[outv]")
    else:
        current = segment_labels[0]
        elapsed = segments[0].out_end_s - segments[0].out_start_s
        for index in range(1, len(segment_labels)):
            transition = transitions[index] if index < len(transitions) else "cut"
            nxt = segment_labels[index]
            seg_len = segments[index].out_end_s - segments[index].out_start_s
            if transition == "xfade" and xfade_s > 1e-6:
                merged = f"xf{index}"
                offset = max(elapsed - xfade_s, 0.0)
                parts.append(
                    f"{current}{nxt}xfade=transition=fade:duration={xfade_s:.6f}:"
                    f"offset={offset:.6f}[{merged}]"
                )
                current = f"[{merged}]"
                elapsed = offset + seg_len
            else:
                merged = f"cat{index}"
                parts.append(f"{current}{nxt}concat=n=2:v=1:a=0[{merged}]")
                current = f"[{merged}]"
                elapsed += seg_len
        parts.append(f"{current}copy[outv]")

    return ";".join(parts)


def render_composite(
    audio_path: Path,
    segments: list[SpeedSegment],
    transitions: list[str],
    *,
    clip_paths: dict[str, Path],
    clip_durations: dict[str, float],
    clip_transforms: dict[str, tuple[int, str, tuple[float, float, float, float] | None]] | None = None,
    music_start_s: float | None,
    music_end_s: float | None,
    out_path: Path,
    hook_text: str | None = None,
    scale: tuple[int, int] = (360, 640),
    temp_dir: Path | None = None,
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
        hook_text=hook_text,
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
        raise RuntimeError(f"Composite preview render failed: {exc}") from exc
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
