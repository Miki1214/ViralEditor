"""Multi-clip virtual reel builder and segment localization."""

from __future__ import annotations

from pathlib import Path

from viral_editor.config import SpeedRampConfig
from viral_editor.models import ClipInput, ClipReel, ClipRole, MediaInfo, ReelEntry, SpeedSegment


def _crop_range(
    clip: ClipInput,
    media: MediaInfo,
) -> tuple[float, float]:
    start = clip.crop_start_s if clip.crop_start_s is not None else 0.0
    end = clip.crop_end_s if clip.crop_end_s is not None else media.duration_s
    start = max(0.0, min(start, media.duration_s))
    end = max(start + 1e-6, min(end, media.duration_s))
    return start, end


def _append_entry(
    entries: list[ReelEntry],
    *,
    clip: ClipInput,
    src_start_s: float,
    src_end_s: float,
    is_hook_loop: bool = False,
) -> None:
    if src_end_s <= src_start_s + 1e-9:
        return
    reel_start = entries[-1].reel_end_s if entries else 0.0
    entries.append(
        ReelEntry(
            clip_id=clip.id,
            path=clip.path,
            reel_start_s=round(reel_start, 6),
            reel_end_s=round(reel_start + (src_end_s - src_start_s), 6),
            src_start_s=round(src_start_s, 6),
            src_end_s=round(src_end_s, 6),
            is_hook_loop=is_hook_loop,
        )
    )


def _source_budget_s(body_output_duration_s: float, config: SpeedRampConfig) -> float:
    if body_output_duration_s <= 0:
        return 0.0
    return body_output_duration_s * config.s_min


def build_reel(
    clips: list[ClipInput],
    clip_media: dict[str, MediaInfo],
    *,
    body_output_duration_s: float,
    speed_config: SpeedRampConfig,
) -> ClipReel:
    """Assemble an ordered virtual reel from clip crops, filler, and hook loops."""
    entries: list[ReelEntry] = []
    by_role: dict[ClipRole, list[ClipInput]] = {"clip": [], "hook": [], "filler": []}
    for clip in sorted(clips, key=lambda item: item.order):
        if not clip.included:
            continue
        by_role[clip.role].append(clip)

    for clip in by_role["clip"]:
        media = clip_media.get(clip.id)
        if media is None:
            continue
        src_start, src_end = _crop_range(clip, media)
        _append_entry(entries, clip=clip, src_start_s=src_start, src_end_s=src_end)

    budget = _source_budget_s(body_output_duration_s, speed_config)
    reel_duration = entries[-1].reel_end_s if entries else 0.0

    def _fill_from_pool(pool: list[ClipInput], *, hook_loop: bool) -> None:
        nonlocal reel_duration
        if not pool:
            return
        index = 0
        safety = 0
        while reel_duration + 1e-6 < budget and safety < 500:
            safety += 1
            clip = pool[index % len(pool)]
            media = clip_media.get(clip.id)
            if media is None:
                index += 1
                continue
            src_start, src_end = _crop_range(clip, media)
            span = src_end - src_start
            if span <= 1e-9:
                index += 1
                continue
            remaining = budget - reel_duration
            if hook_loop and span > remaining + 1e-6:
                src_end = src_start + remaining
            previous_duration = reel_duration
            _append_entry(
                entries,
                clip=clip,
                src_start_s=src_start,
                src_end_s=src_end,
                is_hook_loop=hook_loop,
            )
            if not entries or entries[-1].reel_end_s <= previous_duration + 1e-9:
                break
            reel_duration = entries[-1].reel_end_s
            if not hook_loop:
                index += 1

    if reel_duration + 1e-6 < budget:
        _fill_from_pool(by_role["filler"], hook_loop=False)
        reel_duration = entries[-1].reel_end_s if entries else 0.0
    if reel_duration + 1e-6 < budget:
        _fill_from_pool(by_role["hook"], hook_loop=True)

    return ClipReel(
        entries=entries,
        reel_duration_s=round(entries[-1].reel_end_s if entries else 0.0, 6),
    )


def _entry_for_reel_time(reel: ClipReel, reel_time_s: float) -> ReelEntry | None:
    for entry in reel.entries:
        if entry.reel_start_s <= reel_time_s < entry.reel_end_s - 1e-9:
            return entry
    if reel.entries and reel_time_s >= reel.entries[-1].reel_start_s:
        return reel.entries[-1]
    return None


def localize_segments(segments: list[SpeedSegment], reel: ClipReel) -> list[SpeedSegment]:
    """Split reel-time segments at clip boundaries with per-clip source coordinates."""
    if not reel.entries or not segments:
        return segments

    localized: list[SpeedSegment] = []
    for segment in segments:
        reel_pos = segment.src_start_s
        out_pos = segment.out_start_s
        while reel_pos < segment.src_end_s - 1e-9 and out_pos < segment.out_end_s - 1e-9:
            entry = _entry_for_reel_time(reel, reel_pos)
            if entry is None:
                break
            chunk_reel_end = min(segment.src_end_s, entry.reel_end_s)
            chunk_reel_len = chunk_reel_end - reel_pos
            if chunk_reel_len <= 1e-9:
                next_reel_pos = min(segment.src_end_s, entry.reel_end_s)
                if next_reel_pos <= reel_pos + 1e-9:
                    break
                reel_pos = next_reel_pos
                continue
            chunk_out_len = chunk_reel_len / segment.speed_factor
            chunk_out_end = min(segment.out_end_s, out_pos + chunk_out_len)
            chunk_out_len = chunk_out_end - out_pos
            chunk_reel_len = chunk_out_len * segment.speed_factor
            src_local_start = entry.src_start_s + (reel_pos - entry.reel_start_s)
            localized.append(
                SpeedSegment(
                    out_start_s=round(out_pos, 6),
                    out_end_s=round(out_pos + chunk_out_len, 6),
                    src_start_s=round(src_local_start, 6),
                    src_end_s=round(src_local_start + chunk_reel_len, 6),
                    speed_factor=segment.speed_factor,
                    source_id=entry.clip_id,
                )
            )
            reel_pos += chunk_reel_len
            out_pos += chunk_out_len

    return localized if localized else segments


def hook_clip_for_teaser(clips: list[ClipInput]) -> ClipInput | None:
    hooks = [clip for clip in clips if clip.included and clip.role == "hook"]
    return hooks[0] if hooks else None


def clip_paths_by_id(clips: list[ClipInput]) -> dict[str, Path]:
    return {clip.id: clip.path for clip in clips if clip.included}
