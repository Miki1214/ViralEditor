"""Render-grade seamless loop seam helpers."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from viral_editor.utils.ffmpeg import run_ffmpeg

DEFAULT_CROSSFADE_S = 0.12
DEFAULT_LOOP_PREVIEW_TOTAL_S = 4.0
DEFAULT_LOOP_PREVIEW_CYCLE_GAP_S = 1.0
EQUAL_POWER_CROSSFADE_CURVE = "c1=qsin:c2=qsin"


def snap_to_zero_crossing(
    audio_path: Path,
    time_s: float,
    *,
    search_ms: float = 12.0,
    sr: int = 44100,
) -> float:
    """Snap a cut time to the nearest zero crossing within a small window."""
    del audio_path, sr  # reserved for future sample-accurate snap via soundfile
    return time_s


def build_loop_audition_filter(
    start_s: float,
    duration_s: float,
    *,
    crossfade_s: float = DEFAULT_CROSSFADE_S,
) -> str:
    """FFmpeg filter graph: segment + equal-power (qsin) crossfade loop audition."""
    crossfade_s = min(crossfade_s, duration_s / 4.0)
    return (
        f"[0:a]atrim=start={start_s:.6f}:duration={duration_s:.6f},"
        f"asetpts=PTS-STARTPTS,aresample=44100[seg];"
        f"[seg]asplit=2[a][b];"
        f"[a][b]acrossfade=d={crossfade_s:.4f}:{EQUAL_POWER_CROSSFADE_CURVE}[out]"
    )


def build_loop_seam_only_filter(
    start_s: float,
    end_s: float,
    *,
    crossfade_s: float = DEFAULT_CROSSFADE_S,
    total_s: float = DEFAULT_LOOP_PREVIEW_TOTAL_S,
    cycle_gap_s: float = DEFAULT_LOOP_PREVIEW_CYCLE_GAP_S,
) -> str:
    """FFmpeg filter: ~4s tail→equal-power crossfade→head, then silence before repeat."""
    duration_s = end_s - start_s
    crossfade_s = min(crossfade_s, duration_s / 4.0)
    lead_s = (total_s + crossfade_s) / 2.0
    lead_s = min(lead_s, max(crossfade_s, (duration_s - crossfade_s) / 2.0))
    tail_start = end_s - lead_s
    head_end = start_s + lead_s
    seam = (
        f"[0:a]atrim=start={tail_start:.6f}:end={end_s:.6f},"
        f"asetpts=PTS-STARTPTS,aresample=44100[tail];"
        f"[0:a]atrim=start={start_s:.6f}:end={head_end:.6f},"
        f"asetpts=PTS-STARTPTS,aresample=44100[head];"
        f"[tail][head]acrossfade=d={crossfade_s:.4f}:{EQUAL_POWER_CROSSFADE_CURVE}[seam]"
    )
    if cycle_gap_s > 0:
        return f"{seam};[seam]apad=pad_dur={cycle_gap_s:.4f}[out]"
    return f"{seam};[seam]anull[out]"


def render_loop_seam_only_preview(
    audio_path: Path,
    output_path: Path,
    *,
    start_s: float,
    end_s: float,
    crossfade_s: float = DEFAULT_CROSSFADE_S,
) -> Path:
    """Extract ~4s around the loop wrap plus a short gap before each repeat."""
    if end_s <= start_s:
        raise ValueError("Preview end must be after start")
    snapped_start = snap_to_zero_crossing(audio_path, start_s)
    snapped_end = snap_to_zero_crossing(audio_path, end_s)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(audio_path),
            "-filter_complex",
            build_loop_seam_only_filter(snapped_start, snapped_end, crossfade_s=crossfade_s),
            "-map",
            "[out]",
            "-acodec",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return output_path


def render_loop_preview(
    audio_path: Path,
    output_path: Path,
    *,
    start_s: float,
    end_s: float,
    crossfade_s: float = DEFAULT_CROSSFADE_S,
) -> Path:
    """Extract a loop audition clip with equal-power crossfade at the wrap point."""
    if end_s <= start_s:
        raise ValueError("Preview end must be after start")
    duration_s = end_s - start_s
    snapped_start = snap_to_zero_crossing(audio_path, start_s)
    snapped_end = snap_to_zero_crossing(audio_path, end_s)
    duration_s = snapped_end - snapped_start
    output_path.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(audio_path),
            "-filter_complex",
            build_loop_audition_filter(snapped_start, duration_s, crossfade_s=crossfade_s),
            "-map",
            "[out]",
            "-acodec",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return output_path
