"""Frame-0 teaser clip planner — tail inversion spec for Phase 6."""

from __future__ import annotations

from viral_editor.config import TeaserConfig
from viral_editor.models import ClipInput, MediaInfo, TeaserSpec

# Timing contract (Phase 4 / Phase 6):
# Music plays continuously from output t=0 underneath both teaser and body.
# Total output duration equals the music window; the teaser occupies the first
# ``out_duration_s`` seconds and the speed-ramped body fills the remainder.
#
# Storyboard hook split: when a hook slot exists, the teaser uses the payoff
# segment (last ``duration_s`` of the hook crop). The hook_end slot plays the
# remaining head so the loop reveals the full build-up without duplicating
# the entire clip.


def _hook_crop_range(clip: ClipInput, media: MediaInfo) -> tuple[float, float]:
    start = clip.crop_start_s if clip.crop_start_s is not None else 0.0
    end = clip.crop_end_s if clip.crop_end_s is not None else media.duration_s
    start = max(0.0, min(start, media.duration_s))
    end = max(start + 1e-6, min(end, media.duration_s))
    return start, end


def split_hook_crop(
    crop_start: float,
    crop_end: float,
    tail_fraction: float,
    *,
    min_head_s: float = 0.25,
    min_tail_s: float = 0.1,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Legacy fraction-based split — prefer ``split_hook_crop_by_duration``."""
    duration = max(crop_end - crop_start, 0.0)
    if duration <= 1e-9:
        empty = (crop_start, crop_start)
        return empty, empty

    tail_len = duration * tail_fraction
    tail_len = max(tail_len, min_tail_s)
    tail_len = min(tail_len, max(duration - min_head_s, min_tail_s))
    tail_len = min(tail_len, duration)

    tail_start = crop_end - tail_len
    head_end = max(crop_start, tail_start)
    head = (crop_start, head_end)
    tail = (tail_start, crop_end)
    return head, tail


def split_hook_crop_by_duration(
    crop_start: float,
    crop_end: float,
    payoff_duration_s: float,
    *,
    min_head_s: float = 0.25,
    min_tail_s: float = 0.25,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Legacy source-tail split — prefer ``split_hook_crop_by_output_ratio``."""
    duration = max(crop_end - crop_start, 0.0)
    if duration <= 1e-9:
        empty = (crop_start, crop_start)
        return empty, empty

    payoff_s = max(min(payoff_duration_s, duration - min_head_s), min_tail_s)
    payoff_s = min(payoff_s, duration)
    split = crop_end - payoff_s
    split = max(split, crop_start)
    head = (crop_start, split)
    tail = (split, crop_end)
    return head, tail


def split_hook_crop_by_output_ratio(
    crop_start: float,
    crop_end: float,
    payoff_output_s: float,
    build_output_s: float,
    *,
    min_head_s: float = 0.25,
    min_tail_s: float = 0.25,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Split hook source crop so build + payoff share timestretch (S / total output)."""
    duration = max(crop_end - crop_start, 0.0)
    if duration <= 1e-9:
        empty = (crop_start, crop_start)
        return empty, empty

    total_out = max(payoff_output_s + build_output_s, 1e-9)
    build_src = duration * (build_output_s / total_out)
    build_src = max(min_head_s, min(build_src, duration - min_tail_s))
    split = crop_start + build_src
    head = (crop_start, split)
    tail = (split, crop_end)
    return head, tail


def build_teaser_spec(
    media: MediaInfo,
    config: TeaserConfig,
    *,
    hook_clip: ClipInput | None = None,
    hook_media: MediaInfo | None = None,
    hook_build_output_s: float | None = None,
) -> TeaserSpec:
    """Build a spec for the prepended tail-inversion teaser clip."""
    if hook_clip is not None and hook_media is not None:
        crop_start, crop_end = _hook_crop_range(hook_clip, hook_media)
        build_out = (
            hook_build_output_s
            if hook_build_output_s is not None
            else config.duration_s
        )
        _, (tail_start, tail_end) = split_hook_crop_by_output_ratio(
            crop_start,
            crop_end,
            config.duration_s,
            build_out,
        )
        if tail_end <= tail_start + 1e-9:
            raise ValueError(
                "hook crop is too short for the payoff duration; widen the crop or shorten the hook split"
            )
        return TeaserSpec(
            src_start_s=round(tail_start, 6),
            src_end_s=round(tail_end, 6),
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
