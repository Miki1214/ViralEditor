"""Generate trimmed audio preview clips via FFmpeg."""

from __future__ import annotations

import hashlib
from pathlib import Path

from viral_editor.audio.loop_seam import render_loop_preview, render_loop_seam_only_preview


def preview_cache_path(
    temp_dir: Path,
    *,
    start_s: float,
    end_s: float,
    loop_only: bool = False,
) -> Path:
    mode = "seam-v4" if loop_only else "loop-v4"
    key = hashlib.sha1(f"{mode}-{start_s:.3f}-{end_s:.3f}".encode()).hexdigest()[:12]
    return temp_dir / "previews" / f"preview_{key}.wav"


def ensure_loop_seam_audio(
    audio_path: Path,
    *,
    start_s: float,
    end_s: float,
    temp_dir: Path,
) -> Path:
    """Render-grade seamless loop WAV — equal-power crossfade at the wrap.

    Shared by audition previews, storyboard block player, and video mux.
    """
    return ensure_audio_preview(
        audio_path,
        start_s=start_s,
        end_s=end_s,
        temp_dir=temp_dir,
        loop_only=False,
    )


def ensure_audio_preview(
    audio_path: Path,
    *,
    start_s: float,
    end_s: float,
    temp_dir: Path,
    loop_only: bool = False,
) -> Path:
    """Extract a preview clip — full loop audition or seam-only crossfade."""
    if end_s <= start_s:
        raise ValueError("Preview end must be after start")

    output_path = preview_cache_path(
        temp_dir,
        start_s=start_s,
        end_s=end_s,
        loop_only=loop_only,
    )
    if output_path.is_file() and output_path.stat().st_size > 0:
        return output_path

    if loop_only:
        return render_loop_seam_only_preview(
            audio_path,
            output_path,
            start_s=start_s,
            end_s=end_s,
        )

    return render_loop_preview(
        audio_path,
        output_path,
        start_s=start_s,
        end_s=end_s,
    )
