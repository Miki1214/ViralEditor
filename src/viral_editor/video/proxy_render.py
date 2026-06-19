"""Low-resolution speed-ramp proxy render for UI preview (Phase 6 supersedes)."""

from __future__ import annotations

from pathlib import Path

from viral_editor.models import SpeedRampPlan, SpeedSegment
from viral_editor.utils.ffmpeg import FFmpegError, run_ffmpeg


def _source_trim_spans(
    src_start: float,
    src_end: float,
    src_duration: float,
) -> list[tuple[float, float]]:
    """Expand a possibly wrapped source range into in-bounds trim spans."""
    if src_end <= src_start + 1e-9:
        return []
    if src_duration <= 0:
        return [(src_start, src_end)]

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


def _segment_filter_chains(
    segment: SpeedSegment,
    *,
    src_duration: float,
    width: int,
    height: int,
    label_prefix: str,
) -> tuple[list[str], str]:
    """Build filter chains for one output segment, including source loops."""
    out_len = max(segment.out_end_s - segment.out_start_s, 1e-6)
    speed = max(segment.speed_factor, 1e-6)
    spans = _source_trim_spans(segment.src_start_s, segment.src_end_s, src_duration)

    if not spans:
        spans = [(0.0, min(out_len * speed, max(src_duration, 1e-6)))]

    if len(spans) == 1:
        start, end = spans[0]
        label = label_prefix
        chain = (
            f"[0:v]trim=start={start:.6f}:end={end:.6f},"
            f"setpts=PTS-STARTPTS,"
            f"setpts=PTS/{speed:.6f},"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
            f"trim=duration={out_len:.6f},setpts=PTS-STARTPTS[{label}]"
        )
        return [chain], f"[{label}]"

    parts: list[str] = []
    span_labels: list[str] = []
    span_out_lens: list[float] = []
    total_src = max(segment.src_end_s - segment.src_start_s, 1e-6)

    for index, (start, end) in enumerate(spans):
        span_src = max(end - start, 1e-6)
        span_out = out_len * (span_src / total_src)
        span_labels.append(f"{label_prefix}s{index}")
        span_out_lens.append(span_out)
        parts.append(
            f"[0:v]trim=start={start:.6f}:end={end:.6f},"
            f"setpts=PTS-STARTPTS,"
            f"setpts=PTS/{speed:.6f},"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,"
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
) -> str:
    """Build an ffmpeg filtergraph for segment-wise speed preview."""
    if not plan.segments:
        return f"nullsrc=s={scale[0]}x{scale[1]}:d=0.1,format=yuv420p"

    width, height = scale
    parts: list[str] = []
    concat_inputs: list[str] = []

    for index, segment in enumerate(plan.segments):
        label = f"v{index}"
        chains, concat_ref = _segment_filter_chains(
            segment,
            src_duration=plan.src_duration_s,
            width=width,
            height=height,
            label_prefix=label,
        )
        parts.extend(chains)
        concat_inputs.append(concat_ref)

    parts.append(f"{''.join(concat_inputs)}concat=n={len(plan.segments)}:v=1:a=0[outv]")
    return ";".join(parts)


def render_speed_proxy(
    video_path: Path,
    audio_path: Path,
    plan: SpeedRampPlan,
    *,
    music_start_s: float | None,
    music_end_s: float | None,
    out_path: Path,
    scale: tuple[int, int] = (360, 640),
) -> Path:
    """Render a cached low-res proxy clip with trimmed music mux."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    filtergraph = build_proxy_filtergraph(plan, scale=scale)

    audio_args: list[str] = []
    if music_start_s is not None and music_end_s is not None and music_end_s > music_start_s:
        audio_args = [
            "-ss",
            f"{music_start_s:.6f}",
            "-to",
            f"{music_end_s:.6f}",
        ]

    command = [
        "-y",
        "-i",
        str(video_path),
        *audio_args,
        "-i",
        str(audio_path),
        "-filter_complex",
        filtergraph,
        "-map",
        "[outv]",
        "-map",
        "1:a:0",
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
    try:
        run_ffmpeg(command)
    except FFmpegError as exc:
        raise RuntimeError(f"Speed proxy render failed: {exc}") from exc
    return out_path


def selected_plan_segments(plan: SpeedRampPlan) -> list[SpeedSegment]:
    """Expose segments for tests and callers."""
    return plan.segments
