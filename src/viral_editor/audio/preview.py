"""Generate trimmed audio preview clips via FFmpeg."""

from __future__ import annotations

import hashlib
from pathlib import Path

from viral_editor.audio.block_planner import LOOP_CROSSFADE_S
from viral_editor.utils.ffmpeg import run_ffmpeg


def preview_cache_path(
    temp_dir: Path,
    *,
    start_s: float,
    end_s: float,
) -> Path:
    key = hashlib.sha1(f"loop-v3-{start_s:.3f}-{end_s:.3f}".encode()).hexdigest()[:12]
    return temp_dir / "previews" / f"preview_{key}.wav"


def ensure_audio_preview(
    audio_path: Path,
    *,
    start_s: float,
    end_s: float,
    temp_dir: Path,
) -> Path:
    """Extract a loop-audition clip with a crossfade at the wrap point."""
    if end_s <= start_s:
        raise ValueError("Preview end must be after start")

    output_path = preview_cache_path(temp_dir, start_s=start_s, end_s=end_s)
    if output_path.is_file() and output_path.stat().st_size > 0:
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    duration_s = end_s - start_s
    crossfade_s = min(LOOP_CROSSFADE_S, duration_s / 4.0)
    filter_graph = (
        f"[0:a]atrim=start={start_s:.6f}:duration={duration_s:.6f},"
        f"asetpts=PTS-STARTPTS,aresample=44100[seg];"
        f"[seg]asplit=2[a][b];"
        f"[a][b]acrossfade=d={crossfade_s:.4f}:c1=tri:c2=tri[out]"
    )
    run_ffmpeg(
        [
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(audio_path),
            "-filter_complex",
            filter_graph,
            "-map",
            "[out]",
            "-acodec",
            "pcm_s16le",
            str(output_path),
        ]
    )
    return output_path
