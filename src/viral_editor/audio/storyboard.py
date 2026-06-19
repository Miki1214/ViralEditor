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
from viral_editor.video.teaser import split_hook_crop

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
    slot_count = target_slot_count or max(3, min(8, int(round(duration / 4.0))))
    boundaries = _compute_boundaries(
        window_start,
        window_end,
        downbeats,
        slot_count,
    )

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


_HOOK_MIN_PART_S = 0.25


def _compute_boundaries(
    window_start: float,
    window_end: float,
    downbeats: list[float],
    target_slot_count: int,
) -> list[float]:
    """Pick downbeat-aligned boundaries for ``target_slot_count`` slots in a window."""
    duration = max(window_end - window_start, _MIN_SLOT_S)
    if target_slot_count <= 0:
        return [window_start, window_end]

    local_downbeats = [
        t for t in downbeats if window_start - 1e-6 <= t < window_end - 1e-6
    ]
    if len(local_downbeats) < 2:
        step = duration / max(target_slot_count, 1)
        boundaries = [window_start + step * index for index in range(target_slot_count)]
        boundaries.append(window_end)
        if boundaries[-1] < window_end - 1e-6:
            boundaries[-1] = window_end
        return boundaries

    ideal = duration / target_slot_count
    boundaries = [window_start]
    cursor = window_start
    while cursor < window_end - _MIN_SLOT_S - 1e-6 and len(boundaries) < target_slot_count:
        target = cursor + ideal
        candidates = [t for t in local_downbeats if t > cursor + _MIN_SLOT_S - 1e-6]
        if not candidates:
            break
        next_boundary = min(candidates, key=lambda t: abs(t - target))
        if next_boundary >= window_end - _MIN_SLOT_S:
            break
        boundaries.append(next_boundary)
        cursor = next_boundary
    if boundaries[-1] < window_end - 1e-6:
        boundaries.append(window_end)
    while len(boundaries) < target_slot_count + 1:
        boundaries.append(window_end)
    return boundaries[: target_slot_count + 1]


def _relative_downbeats(
    features: BeatSyncFeatures | None,
    *,
    music_start_s: float,
    music_end_s: float,
) -> list[float]:
    if features is None:
        return [0.0]
    absolute = _downbeats_in_window(features, music_start_s, music_end_s)
    if not absolute:
        return [0.0]
    return [round(t - music_start_s, 6) for t in absolute]


def _snap_time_to_downbeat(
    time_s: float,
    downbeats: list[float],
    *,
    min_s: float,
    max_s: float,
) -> float:
    clamped = max(min_s, min(max_s, time_s))
    candidates = [t for t in downbeats if min_s - 1e-6 <= t <= max_s + 1e-6]
    if not candidates:
        return round(clamped, 6)
    return round(min(candidates, key=lambda t: abs(t - clamped)), 6)


def _slot_from_boundary(
    slot: StorySlot,
    *,
    start_s: float,
    end_s: float,
) -> StorySlot:
    duration = max(end_s - start_s, _MIN_SLOT_S)
    end_s = start_s + duration
    return slot.model_copy(
        update={
            "out_start_s": round(start_s, 6),
            "out_end_s": round(end_s, 6),
            "target_duration_s": round(duration, 6),
        }
    )


def relayout_beat_aligned_timeline(
    slots: list[StorySlot],
    *,
    total_duration_s: float,
    features: BeatSyncFeatures | None = None,
    music_start_s: float = 0.0,
    music_end_s: float | None = None,
) -> list[StorySlot]:
    """Place slot windows on the music block grid instead of sequential packing."""
    if music_end_s is None:
        music_end_s = total_duration_s
    ordered = sorted(slots, key=lambda slot: slot.order)
    if not ordered:
        return []

    downbeats = _relative_downbeats(
        features,
        music_start_s=music_start_s,
        music_end_s=music_end_s,
    )
    if not downbeats or downbeats[0] > 1e-6:
        downbeats = [0.0, *downbeats]
    if downbeats[-1] < total_duration_s - 1e-6:
        downbeats.append(round(total_duration_s, 6))

    hook_start = next((slot for slot in ordered if slot.role == "hook_start"), None)
    hook_end = next((slot for slot in ordered if slot.role == "hook_end"), None)
    hook = next((slot for slot in ordered if slot.role == "hook"), None)
    middle = [
        slot
        for slot in ordered
        if slot.role not in ("hook", "hook_start", "hook_end")
    ]

    if hook_start is not None and hook_end is not None:
        hook_budget = hook_start.target_duration_s + hook_end.target_duration_s
        payoff_end = _snap_time_to_downbeat(
            hook_start.target_duration_s,
            downbeats,
            min_s=_HOOK_MIN_PART_S,
            max_s=max(hook_budget - _HOOK_MIN_PART_S, _HOOK_MIN_PART_S),
        )
        build_start = _snap_time_to_downbeat(
            total_duration_s - hook_end.target_duration_s,
            downbeats,
            min_s=payoff_end + _MIN_SLOT_S * max(len(middle), 1),
            max_s=total_duration_s - _HOOK_MIN_PART_S,
        )
        if build_start <= payoff_end + _MIN_SLOT_S * 0.5:
            payoff_end = round(min(hook_start.target_duration_s, hook_budget - _HOOK_MIN_PART_S), 6)
            build_start = round(total_duration_s - hook_end.target_duration_s, 6)

        relaid = [
            _slot_from_boundary(hook_start, start_s=0.0, end_s=payoff_end),
        ]
        if middle:
            bounds = _compute_boundaries(
                payoff_end,
                build_start,
                downbeats,
                len(middle),
            )
            for index, slot in enumerate(middle):
                relaid.append(
                    _slot_from_boundary(
                        slot,
                        start_s=bounds[index],
                        end_s=bounds[index + 1],
                    )
                )
        relaid.append(
            _slot_from_boundary(
                hook_end,
                start_s=build_start,
                end_s=total_duration_s,
            )
        )
        return relaid

    if hook is not None:
        slot_count = 1 + len(middle)
        bounds = _compute_boundaries(0.0, total_duration_s, downbeats, slot_count)
        relaid = [
            _slot_from_boundary(hook, start_s=bounds[0], end_s=bounds[1]),
        ]
        for index, slot in enumerate(middle):
            relaid.append(
                _slot_from_boundary(
                    slot,
                    start_s=bounds[index + 1],
                    end_s=bounds[index + 2],
                )
            )
        return relaid

    return relayout_slot_timeline(slots)


def relayout_slot_timeline(slots: list[StorySlot]) -> list[StorySlot]:
    """Recompute out_start_s/out_end_s from ordered target durations."""
    ordered = sorted(slots, key=lambda slot: slot.order)
    cursor = 0.0
    relaid: list[StorySlot] = []
    for slot in ordered:
        duration = slot.target_duration_s
        relaid.append(
            slot.model_copy(
                update={
                    "out_start_s": round(cursor, 6),
                    "out_end_s": round(cursor + duration, 6),
                }
            )
        )
        cursor += duration
    return relaid


def _full_hook_crop(start: StorySlot | None, end: StorySlot | None) -> tuple[float, float]:
    if start is None and end is None:
        return 0.0, 0.0
    starts = [slot.crop_start_s for slot in (start, end) if slot and slot.crop_start_s is not None]
    ends = [slot.crop_end_s for slot in (start, end) if slot and slot.crop_end_s is not None]
    if not starts or not ends:
        return 0.0, 1.0
    return min(starts), max(ends)


def apply_hook_inversion_layout(
    storyboard: Storyboard,
    *,
    enabled: bool,
    payoff_duration_s: float,
    tail_fraction: float,
    features: BeatSyncFeatures | None = None,
) -> Storyboard:
    """Split the hook into start/end storyboard slots aligned to the music block."""
    slots = sorted(storyboard.slots, key=lambda slot: slot.order)
    hook = next((slot for slot in slots if slot.role == "hook"), None)
    hook_start = next((slot for slot in slots if slot.role == "hook_start"), None)
    hook_end = next((slot for slot in slots if slot.role == "hook_end"), None)
    middle = [
        slot
        for slot in slots
        if slot.role not in ("hook", "hook_start", "hook_end")
    ]

    if not enabled:
        if hook_start is None and hook_end is None:
            return storyboard
        base = hook_start or hook_end
        assert base is not None
        root_id = base.id.replace("_hook_start", "").replace("_hook_end", "")
        crop_start, crop_end = _full_hook_crop(hook_start, hook_end)
        merged = base.model_copy(
            update={
                "id": root_id,
                "order": 0,
                "label": "Hook",
                "role": "hook",
                "target_duration_s": round(
                    (hook_start.target_duration_s if hook_start else 0.0)
                    + (hook_end.target_duration_s if hook_end else 0.0),
                    6,
                ),
                "transition_in": "cut",
                "crop_start_s": round(crop_start, 6),
                "crop_end_s": round(crop_end, 6),
            }
        )
        reordered = [merged]
        for index, slot in enumerate(middle):
            reordered.append(slot.model_copy(update={"order": index + 1}))
        relaid = relayout_beat_aligned_timeline(
            reordered,
            total_duration_s=storyboard.total_duration_s,
            features=features,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
        )
        total = relaid[-1].out_end_s if relaid else storyboard.total_duration_s
        return storyboard.model_copy(update={"slots": relaid, "total_duration_s": total})

    if hook is None and hook_start is None:
        return storyboard

    base = hook or hook_start or hook_end
    assert base is not None
    root_id = base.id.replace("_hook_start", "").replace("_hook_end", "")
    if hook is not None:
        hook_budget = hook.target_duration_s
        crop_start = hook.crop_start_s if hook.crop_start_s is not None else 0.0
        crop_end = hook.crop_end_s if hook.crop_end_s is not None else crop_start + hook_budget
    else:
        hook_budget = (hook_start.target_duration_s if hook_start else 0.0) + (
            hook_end.target_duration_s if hook_end else 0.0
        )
        crop_start, crop_end = _full_hook_crop(hook_start, hook_end)

    payoff_d = min(max(payoff_duration_s, _HOOK_MIN_PART_S), hook_budget - _HOOK_MIN_PART_S)
    build_d = hook_budget - payoff_d
    head, tail = split_hook_crop(crop_start, crop_end, tail_fraction)

    start_slot = base.model_copy(
        update={
            "id": f"{root_id}_hook_start",
            "order": 0,
            "label": "Hook · start",
            "role": "hook_start",
            "target_duration_s": round(payoff_d, 6),
            "transition_in": "cut",
            "crop_start_s": round(tail[0], 6),
            "crop_end_s": round(tail[1], 6),
        }
    )
    end_slot = base.model_copy(
        update={
            "id": f"{root_id}_hook_end",
            "order": len(middle) + 1,
            "label": "Hook · end",
            "role": "hook_end",
            "target_duration_s": round(build_d, 6),
            "transition_in": middle[-1].transition_in if middle else "cut",
            "crop_start_s": round(head[0], 6),
            "crop_end_s": round(head[1], 6),
        }
    )
    reordered = [start_slot]
    for index, slot in enumerate(middle):
        reordered.append(slot.model_copy(update={"order": index + 1}))
    reordered.append(end_slot.model_copy(update={"order": len(middle) + 1}))
    relaid = relayout_beat_aligned_timeline(
        reordered,
        total_duration_s=storyboard.total_duration_s,
        features=features,
        music_start_s=storyboard.music_start_s,
        music_end_s=storyboard.music_end_s,
    )
    total = relaid[-1].out_end_s if relaid else storyboard.total_duration_s
    return storyboard.model_copy(update={"slots": relaid, "total_duration_s": total})


def storyboard_to_segments(
    storyboard: Storyboard,
    clip_media: dict[str, MediaInfo],
) -> tuple[list[SpeedSegment], list[str], list[str]]:
    """Map assigned slots to speed segments, roles, and parallel slot ids."""
    segments: list[SpeedSegment] = []
    roles: list[str] = []
    slot_ids: list[str] = []
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
        roles.append(slot.role)
        slot_ids.append(slot.id)
        out_cursor += out_duration
    return segments, roles, slot_ids


def assigned_storyboard_slots(storyboard: Storyboard) -> list[StorySlot]:
    """Slots with clips in storyboard playback order."""
    return [
        slot
        for slot in sorted(storyboard.slots, key=lambda item: item.order)
        if slot.assigned_clip_id
    ]


def storyboard_filled_enough(storyboard: Storyboard) -> bool:
    """True when the hook (or hook start) slot has a clip assigned."""
    return any(
        slot.role in ("hook", "hook_start") and slot.assigned_clip_id
        for slot in storyboard.slots
    )


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
