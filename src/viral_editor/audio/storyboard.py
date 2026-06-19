"""Storyboard planner — partition a music block into timed clip slots."""

from __future__ import annotations

import bisect

from viral_editor.audio.features import BeatSyncFeatures
from viral_editor.models import (
    MediaInfo,
    MusicBlock,
    MusicSection,
    SpeedSegment,
    Storyboard,
    StorySlot,
    Transient,
)

_MIN_SLOT_S = 1.5
_DEFAULT_XFADE_S = 0.25
_PUNCH_SPEED = 0.65


def _downbeats_in_window(
    features: BeatSyncFeatures | None,
    start_s: float,
    end_s: float,
) -> list[float]:
    if features is None:
        return []
    beats = [float(t) for t in features.downbeat_times_s.tolist()]
    return [t for t in beats if start_s - 1e-6 <= t < end_s - 1e-6]


def _drop_counts_by_slot(
    transients: list[Transient],
    boundaries: list[float],
) -> list[int]:
    counts = [0] * max(len(boundaries) - 1, 0)
    for transient in transients:
        if transient.type != "drop":
            continue
        t = transient.timestamp_ms / 1000.0
        index = bisect.bisect_right(boundaries, t) - 1
        if 0 <= index < len(counts):
            counts[index] += 1
    return counts


def _slot_labels(role: str, index: int, total: int) -> str:
    if role == "hook":
        return "Hook"
    if role == "punch":
        return "Strongest punch"
    clip_index = index
    if index > 0:
        clip_index = index
    return f"Clip {clip_index}" if role == "clip" else f"Slot {index + 1}"


def plan_storyboard(
    block: MusicBlock,
    *,
    features: BeatSyncFeatures | None = None,
    sections: list[MusicSection] | None = None,
    transients: list[Transient] | None = None,
    target_slot_count: int | None = None,
) -> Storyboard:
    """Partition a music block into downbeat-aligned slots."""
    del sections  # reserved for future section-aware labels
    window_start = block.start_s
    window_end = block.end_s
    duration = max(window_end - window_start, _MIN_SLOT_S)

    downbeats = _downbeats_in_window(features, window_start, window_end)
    if len(downbeats) < 2:
        step = duration / max(target_slot_count or 4, 3)
        boundaries = [window_start + step * index for index in range(int(duration / step) + 1)]
        if boundaries[-1] < window_end - 1e-6:
            boundaries.append(window_end)
    else:
        slot_count = target_slot_count or max(3, min(8, int(round(duration / 4.0))))
        ideal = duration / slot_count
        boundaries = [window_start]
        cursor = window_start
        while cursor < window_end - _MIN_SLOT_S - 1e-6 and len(boundaries) < slot_count:
            target = cursor + ideal
            candidates = [t for t in downbeats if t > cursor + _MIN_SLOT_S - 1e-6]
            if not candidates:
                break
            next_boundary = min(candidates, key=lambda t: abs(t - target))
            if next_boundary >= window_end - _MIN_SLOT_S:
                break
            boundaries.append(next_boundary)
            cursor = next_boundary
        if boundaries[-1] < window_end - 1e-6:
            boundaries.append(window_end)

    drop_counts = _drop_counts_by_slot(transients or [], boundaries)
    punch_index = drop_counts.index(max(drop_counts)) if drop_counts else -1

    slots: list[StorySlot] = []
    for index in range(len(boundaries) - 1):
        start = boundaries[index]
        end = boundaries[index + 1]
        slot_duration = max(end - start, _MIN_SLOT_S)
        if index == 0:
            role = "hook"
        elif index == punch_index and punch_index > 0:
            role = "punch"
        else:
            role = "clip"
        slots.append(
            StorySlot(
                id=f"slot_{index}",
                order=index,
                label=_slot_labels(role, index, len(boundaries) - 1),
                role=role,
                out_start_s=round(start - window_start, 6),
                out_end_s=round(end - window_start, 6),
                target_duration_s=round(slot_duration, 6),
                transition_in="xfade" if index > 0 else "cut",
            )
        )

    return Storyboard(
        music_block_id=block.id,
        music_start_s=round(window_start, 6),
        music_end_s=round(window_end, 6),
        total_duration_s=round(duration, 6),
        loop_to_hook=True,
        slots=slots,
    )


def storyboard_to_segments(
    storyboard: Storyboard,
    clip_media: dict[str, MediaInfo],
) -> list[SpeedSegment]:
    """Map assigned slots to speed segments for compositing."""
    segments: list[SpeedSegment] = []
    out_cursor = 0.0
    for slot in sorted(storyboard.slots, key=lambda item: item.order):
        if slot.assigned_clip_id is None:
            continue
        media = clip_media.get(slot.assigned_clip_id)
        if media is None:
            continue
        crop_start = slot.crop_start_s if slot.crop_start_s is not None else 0.0
        crop_end = (
            slot.crop_end_s if slot.crop_end_s is not None else media.duration_s
        )
        crop_start = max(0.0, min(crop_start, media.duration_s))
        crop_end = max(crop_start + 1e-6, min(crop_end, media.duration_s))
        crop_duration = crop_end - crop_start
        out_duration = max(slot.target_duration_s, 1e-6)
        speed = crop_duration / out_duration
        if slot.role == "punch":
            speed *= _PUNCH_SPEED
        segments.append(
            SpeedSegment(
                out_start_s=round(out_cursor, 6),
                out_end_s=round(out_cursor + out_duration, 6),
                src_start_s=round(crop_start, 6),
                src_end_s=round(crop_end, 6),
                speed_factor=round(max(speed, 1e-6), 6),
                source_id=slot.assigned_clip_id,
            )
        )
        out_cursor += out_duration
    return segments


def storyboard_filled_enough(storyboard: Storyboard) -> bool:
    """True when the hook slot has a clip assigned (minimum composited preview)."""
    return any(slot.role == "hook" and slot.assigned_clip_id for slot in storyboard.slots)


def xfade_overlap_s(storyboard: Storyboard) -> float:
    """Total timeline compression from crossfade overlaps."""
    overlap = 0.0
    for slot in storyboard.slots:
        if slot.order > 0 and slot.transition_in == "xfade":
            overlap += _DEFAULT_XFADE_S
    return overlap


def effective_output_duration(storyboard: Storyboard) -> float:
    return max(storyboard.total_duration_s - xfade_overlap_s(storyboard), 1e-6)


def merge_storyboard_updates(
    existing: Storyboard,
    updates: list[StorySlot],
) -> Storyboard:
    """Apply slot field updates while preserving assignments."""
    by_id = {slot.id: slot for slot in existing.slots}
    for update in updates:
        current = by_id.get(update.id)
        if current is None:
            continue
        by_id[update.id] = current.model_copy(
            update={
                "order": update.order,
                "label": update.label,
                "role": update.role,
                "out_start_s": update.out_start_s,
                "out_end_s": update.out_end_s,
                "target_duration_s": update.target_duration_s,
                "transition_in": update.transition_in,
            }
        )
    ordered = sorted(by_id.values(), key=lambda slot: slot.order)
    total = ordered[-1].out_end_s if ordered else existing.total_duration_s
    return existing.model_copy(update={"slots": ordered, "total_duration_s": total})
