"""Frame-0 teaser clip planner — tail inversion spec for Phase 6."""

from __future__ import annotations

from viral_editor.config import TeaserConfig
from viral_editor.models import ClipInput, MediaInfo, TeaserSpec

# Timing contract (Phase 4 / Phase 6):
# Music plays continuously from output t=0 underneath both teaser and body.
# Total output duration equals the music window; the teaser occupies the first
# ``out_duration_s`` seconds and the speed-ramped body fills the remainder.


def _hook_crop_range(clip: ClipInput, media: MediaInfo) -> tuple[float, float]:
    start = clip.crop_start_s if clip.crop_start_s is not None else 0.0
    end = clip.crop_end_s if clip.crop_end_s is not None else media.duration_s
    start = max(0.0, min(start, media.duration_s))
    end = max(start + 1e-6, min(end, media.duration_s))
    return start, end


def build_teaser_spec(
    media: MediaInfo,
    config: TeaserConfig,
    *,
    hook_clip: ClipInput | None = None,
    hook_media: MediaInfo | None = None,
) -> TeaserSpec:
    """Build a spec for the prepended tail-inversion teaser clip."""
    if hook_clip is not None and hook_media is not None:
        src_start_s, src_end_s = _hook_crop_range(hook_clip, hook_media)
        return TeaserSpec(
            src_start_s=round(src_start_s, 6),
            src_end_s=round(src_end_s, 6),
            out_duration_s=config.duration_s,
            mask=config.mask,
            source_id=hook_clip.id,
            source_path=hook_clip.path,
        )

    src_duration_s = media.duration_s
    if src_duration_s <= 0:
        raise ValueError("video duration must be positive to build a teaser")

    src_start_s = src_duration_s * (1.0 - config.tail_fraction)
    src_end_s = src_duration_s
    if src_end_s <= src_start_s + 1e-9:
        raise ValueError(
            "teaser tail_fraction yields an empty source range; increase tail_fraction or use longer video"
        )

    return TeaserSpec(
        src_start_s=round(src_start_s, 6),
        src_end_s=round(src_end_s, 6),
        out_duration_s=config.duration_s,
        mask=config.mask,
    )


def teaser_body_output_duration(
    music_window_duration_s: float,
    teaser: TeaserSpec,
) -> float:
    """Return output seconds available for the speed-ramped body after the teaser."""
    return max(0.0, music_window_duration_s - teaser.out_duration_s)
