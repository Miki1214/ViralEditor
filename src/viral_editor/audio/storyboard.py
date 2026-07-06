"""Storyboard planner — partition a music block into timed clip slots."""

from __future__ import annotations

import bisect
from dataclasses import dataclass

import numpy as np

from viral_editor.audio.features import BeatSyncFeatures
from viral_editor.editing.retention_policy import (
    EARLY_HOOK_FX_BY_S,
    HOOK_WINDOW_S,
    INTERRUPT_MAX_GAP_S,
    INTERRUPT_MIN_GAP_S,
    SURGE_SCORE_THRESHOLD,
    find_energy_peaks,
    find_flux_peaks,
    place_interrupts,
    score_plan,
)
from viral_editor.models import (
    FxEvent,
    MediaInfo,
    MusicBlock,
    MusicSection,
    RetentionPlanScore,
    SpeedSegment,
    Storyboard,
    StorySlot,
    Transient,
)
from viral_editor.video.teaser import split_hook_crop_by_output_ratio

_MIN_SLOT_S = 1.5
_DEFAULT_XFADE_S = 0.25
_PUNCH_SPEED = 0.65
_MAX_SLOT_COUNT = 8
_SLOT_HARD_FLOOR_S = 2.0
_SLOT_HARD_CEIL_S = 6.5
_CANDIDATE_DEDUPE_S = 0.12


@dataclass(frozen=True)
class _SalientCut:
    time_s: float
    magnitude: float
    reason: str


@dataclass(frozen=True)
class _BoundaryPlan:
    boundaries: list[float]
    slot_reasons: list[str | None]


def _soft_count_range(duration: float, target_slot_count: int) -> tuple[int, int]:
    """Soft slot-count band around the user's Slots chip."""
    max_fit = max(1, int(duration / _MIN_SLOT_S))
    lo = max(1, min(target_slot_count - 1, max_fit))
    hi = max(1, min(target_slot_count + 2, _MAX_SLOT_COUNT, max_fit))
    if lo > hi:
        lo = hi
    return lo, hi


def _recommended_slot_count(duration: float, target_slot_count: int | None = None) -> int:
    """Pick a slot count that fits the block without forcing extra clips on short tracks."""
    max_fit = max(1, int(duration / _MIN_SLOT_S))
    if target_slot_count is not None:
        return max(1, min(target_slot_count, max_fit))
    ideal = max(1, min(_MAX_SLOT_COUNT, int(round(duration / 4.0))))
    return max(1, min(ideal, max_fit))


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
    scope_lanes: dict[str, np.ndarray] | None = None,
) -> Storyboard:
    """Partition a music block into downbeat-aligned slots."""
    del sections  # reserved for future section-aware labels
    window_start = block.start_s
    window_end = block.end_s
    duration = max(window_end - window_start, _MIN_SLOT_S)

    downbeats = _downbeats_in_window(features, window_start, window_end)
    slot_count = _recommended_slot_count(duration, target_slot_count)
    boundary_plan = _compute_boundaries(
        window_start,
        window_end,
        downbeats,
        slot_count,
        scope_lanes=scope_lanes,
        absolute_downbeats=(
            features.downbeat_times_s.tolist() if features is not None else []
        ),
    )
    boundaries = boundary_plan.boundaries

    drop_counts = _drop_counts_by_slot(transients or [], boundaries)
    punch_index = drop_counts.index(max(drop_counts)) if drop_counts else -1

    slot_rationales = _slot_rationales(
        boundaries,
        window_start,
        scope_lanes=scope_lanes,
        absolute_downbeats=(
            features.downbeat_times_s.tolist() if features is not None else []
        ),
        slot_reasons=boundary_plan.slot_reasons,
    )

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
                rationale=slot_rationales[index] if index < len(slot_rationales) else None,
            )
        )

    retention_score: RetentionPlanScore | None = None
    if features is not None:
        interrupts = place_interrupts(
            scope_lanes,
            features.downbeat_times_s.tolist(),
            window_start_s=window_start,
            window_end_s=window_end,
        )
        retention_score = score_plan(
            scope_lanes,
            features.downbeat_times_s.tolist(),
            interrupts,
            window_start_s=window_start,
            window_end_s=window_end,
        )

    return Storyboard(
        music_block_id=block.id,
        music_start_s=round(window_start, 6),
        music_end_s=round(window_end, 6),
        total_duration_s=round(duration, 6),
        loop_to_hook=True,
        slots=slots,
        retention_score=retention_score,
    )


_HOOK_MIN_PART_S = 0.25


def _slot_rationales(
    boundaries: list[float],
    window_start: float,
    *,
    scope_lanes: dict[str, np.ndarray] | None,
    absolute_downbeats: list[float],
    slot_reasons: list[str | None] | None = None,
) -> list[str | None]:
    if slot_reasons is not None and len(slot_reasons) == max(len(boundaries) - 1, 0):
        return list(slot_reasons)

    rationales: list[str | None] = []
    peaks = find_energy_peaks(
        scope_lanes,
        absolute_downbeats,
        window_start_s=window_start,
        window_end_s=boundaries[-1] if boundaries else window_start,
    )
    peak_times = {round(peak.time_s, 3) for peak in peaks}
    for index in range(len(boundaries) - 1):
        start = boundaries[index]
        rel_start = start - window_start
        if index == 0:
            rationales.append(
                f"Hook slot — aim FX by {EARLY_HOOK_FX_BY_S:.0f}s"
                if rel_start <= HOOK_WINDOW_S
                else "Hook slot"
            )
            continue
        near_peak = any(abs(start - pt) <= 0.2 for pt in peak_times)
        gap = start - boundaries[index - 1]
        if near_peak and INTERRUPT_MIN_GAP_S <= gap <= INTERRUPT_MAX_GAP_S + 0.5:
            rationales.append(f"Energy peak boundary @ {rel_start:.2f}s")
        elif near_peak:
            rationales.append(f"Snapped to energy peak @ {rel_start:.2f}s")
        else:
            rationales.append(f"Downbeat boundary @ {rel_start:.2f}s")
    return rationales


def _nearest_time_in_range(
    target_s: float,
    candidates: list[float],
    *,
    min_s: float,
    max_s: float,
) -> float:
    in_range = [value for value in candidates if min_s - 1e-6 <= value <= max_s + 1e-6]
    if not in_range:
        return round((min_s + max_s) / 2.0, 6)
    return round(min(in_range, key=lambda value: abs(value - target_s)), 6)


def _collect_salient_candidates(
    *,
    window_start: float,
    window_end: float,
    scope_lanes: dict[str, np.ndarray],
    absolute_downbeats: list[float],
) -> list[_SalientCut]:
    candidates: list[_SalientCut] = []
    for peak in find_energy_peaks(
        scope_lanes,
        absolute_downbeats,
        window_start_s=window_start,
        window_end_s=window_end,
    ):
        rel = peak.time_s - window_start
        if peak.surge_score >= SURGE_SCORE_THRESHOLD:
            label = "Energy surge"
        else:
            label = "RMS peak"
        if peak.on_downbeat:
            label += " on downbeat"
        candidates.append(
            _SalientCut(
                time_s=peak.time_s,
                magnitude=peak.magnitude,
                reason=f"{label} @ {rel:.2f}s",
            )
        )
    for band in ("low", "high"):
        for peak in find_flux_peaks(
            scope_lanes,
            band,
            window_start_s=window_start,
            window_end_s=window_end,
        ):
            rel = peak.time_s - window_start
            candidates.append(
                _SalientCut(
                    time_s=peak.time_s,
                    magnitude=peak.magnitude,
                    reason=f"{band.capitalize()}-band flux @ {rel:.2f}s",
                )
            )

    candidates.sort(key=lambda cut: (-cut.magnitude, cut.time_s))
    deduped: list[_SalientCut] = []
    for cut in candidates:
        if window_start - 1e-6 <= cut.time_s < window_end - 1e-6 and all(
            abs(cut.time_s - kept.time_s) >= _CANDIDATE_DEDUPE_S for kept in deduped
        ):
            deduped.append(cut)
    deduped.sort(key=lambda cut: cut.time_s)
    return deduped


def _greedy_salient_cuts(
    *,
    window_start: float,
    window_end: float,
    candidates: list[_SalientCut],
    beat_grid: list[float],
) -> tuple[list[float], list[_SalientCut]]:
    boundaries = [round(window_start, 6)]
    cuts: list[_SalientCut] = []
    while True:
        cursor = boundaries[-1]
        remaining = window_end - cursor
        if remaining <= _MIN_SLOT_S + 1e-6:
            break
        if remaining <= _SLOT_HARD_FLOOR_S + 1e-6:
            break

        hard_min = cursor + _SLOT_HARD_FLOOR_S
        hard_max = min(cursor + _SLOT_HARD_CEIL_S, window_end - _MIN_SLOT_S)
        ideal_min = cursor + INTERRUPT_MIN_GAP_S
        ideal_max = min(cursor + INTERRUPT_MAX_GAP_S, hard_max)

        pool = [cut for cut in candidates if hard_min - 1e-6 <= cut.time_s <= hard_max + 1e-6]
        ideal_pool = [
            cut for cut in pool if ideal_min - 1e-6 <= cut.time_s <= ideal_max + 1e-6
        ]
        pick: _SalientCut | None = None
        if ideal_pool:
            pick = max(ideal_pool, key=lambda cut: cut.magnitude)
        elif pool:
            pick = max(pool, key=lambda cut: cut.magnitude)
        elif remaining > _SLOT_HARD_CEIL_S:
            target = cursor + (INTERRUPT_MIN_GAP_S + INTERRUPT_MAX_GAP_S) / 2.0
            cut_time = _nearest_time_in_range(
                target,
                beat_grid,
                min_s=hard_min,
                max_s=hard_max,
            )
            rel = cut_time - window_start
            pick = _SalientCut(
                time_s=cut_time,
                magnitude=0.0,
                reason=f"Cadence fill @ {rel:.2f}s",
            )
        else:
            break

        if pick.time_s >= window_end - _MIN_SLOT_S:
            break
        boundaries.append(round(pick.time_s, 6))
        cuts.append(pick)

    boundaries.append(round(window_end, 6))
    return boundaries, cuts


def _clamp_boundary_count(
    boundaries: list[float],
    cuts: list[_SalientCut],
    *,
    lo: int,
    hi: int,
    window_start: float,
    beat_grid: list[float],
) -> tuple[list[float], list[_SalientCut]]:
    while len(boundaries) - 1 > hi and len(cuts) > 0:
        drop_index = min(
            range(len(cuts)),
            key=lambda index: (cuts[index].magnitude, cuts[index].time_s),
        )
        drop_time = cuts[drop_index].time_s
        boundary_index = boundaries.index(round(drop_time, 6))
        boundaries.pop(boundary_index)
        cuts.pop(drop_index)

    while len(boundaries) - 1 < lo:
        spans = [
            (boundaries[index + 1] - boundaries[index], index)
            for index in range(len(boundaries) - 1)
        ]
        if not spans:
            break
        span, index = max(spans, key=lambda item: item[0])
        if span < 2.0 * _SLOT_HARD_FLOOR_S:
            break
        start = boundaries[index]
        end = boundaries[index + 1]
        target = start + span / 2.0
        cut_time = _nearest_time_in_range(
            target,
            beat_grid,
            min_s=start + _SLOT_HARD_FLOOR_S,
            max_s=end - _SLOT_HARD_FLOOR_S,
        )
        if cut_time <= start + _MIN_SLOT_S or cut_time >= end - _MIN_SLOT_S:
            break
        rel = cut_time - window_start
        boundaries.insert(index + 1, round(cut_time, 6))
        cuts.insert(
            index,
            _SalientCut(
                time_s=cut_time,
                magnitude=0.0,
                reason=f"Cadence fill @ {rel:.2f}s",
            ),
        )

    return boundaries, cuts


def _slot_reasons_from_cuts(
    boundaries: list[float],
    cuts: list[_SalientCut],
    *,
    window_start: float,
) -> list[str | None]:
    cut_by_time = {round(cut.time_s, 6): cut for cut in cuts}
    reasons: list[str | None] = []
    for index in range(len(boundaries) - 1):
        if index == 0:
            reasons.append(
                f"Hook slot — aim FX by {EARLY_HOOK_FX_BY_S:.0f}s"
                if boundaries[0] - window_start <= HOOK_WINDOW_S
                else "Hook slot"
            )
            continue
        cut = cut_by_time.get(round(boundaries[index], 6))
        if cut is not None:
            reasons.append(cut.reason)
        else:
            rel = boundaries[index] - window_start
            reasons.append(f"Cadence fill @ {rel:.2f}s")
    return reasons


def _salient_boundaries(
    window_start: float,
    window_end: float,
    *,
    downbeats: list[float],
    scope_lanes: dict[str, np.ndarray],
    absolute_downbeats: list[float],
    soft_count_range: tuple[int, int],
) -> _BoundaryPlan:
    duration = max(window_end - window_start, _MIN_SLOT_S)
    lo, hi = soft_count_range
    abs_downbeats = absolute_downbeats or [
        window_start + value for value in downbeats
    ]
    beat_grid = sorted(
        {
            round(value, 6)
            for value in abs_downbeats
            if window_start - 1e-6 <= value <= window_end + 1e-6
        }
    )
    if not beat_grid or beat_grid[0] > window_start + 1e-6:
        beat_grid = [round(window_start, 6), *beat_grid]
    if beat_grid[-1] < window_end - 1e-6:
        beat_grid.append(round(window_end, 6))

    candidates = _collect_salient_candidates(
        window_start=window_start,
        window_end=window_end,
        scope_lanes=scope_lanes,
        absolute_downbeats=abs_downbeats,
    )
    boundaries, cuts = _greedy_salient_cuts(
        window_start=window_start,
        window_end=window_end,
        candidates=candidates,
        beat_grid=beat_grid,
    )
    boundaries, cuts = _clamp_boundary_count(
        boundaries,
        cuts,
        lo=lo,
        hi=hi,
        window_start=window_start,
        beat_grid=beat_grid,
    )

    spans = [
        boundaries[index + 1] - boundaries[index]
        for index in range(len(boundaries) - 1)
    ]
    if not spans or any(span < _MIN_SLOT_S - 1e-6 for span in spans):
        fallback_count = max(lo, min(hi, lo))
        step = duration / fallback_count
        boundaries = [round(window_start + step * index, 6) for index in range(fallback_count)]
        boundaries.append(round(window_end, 6))
        cuts = []
    elif any(span > _SLOT_HARD_CEIL_S + 1e-3 for span in spans):
        repaired: list[float] = [round(window_start, 6)]
        repaired_cuts: list[_SalientCut] = []
        cursor = window_start
        while cursor < window_end - _MIN_SLOT_S:
            remaining = window_end - cursor
            if remaining <= _SLOT_HARD_CEIL_S + 1e-6:
                break
            hard_max = min(cursor + _SLOT_HARD_CEIL_S, window_end - _MIN_SLOT_S)
            pool = [
                cut for cut in candidates
                if cursor + _SLOT_HARD_FLOOR_S - 1e-6 <= cut.time_s <= hard_max + 1e-6
            ]
            if pool:
                pick = max(pool, key=lambda cut: cut.magnitude)
            else:
                target = cursor + (INTERRUPT_MIN_GAP_S + INTERRUPT_MAX_GAP_S) / 2.0
                cut_time = _nearest_time_in_range(
                    target,
                    beat_grid,
                    min_s=cursor + _SLOT_HARD_FLOOR_S,
                    max_s=hard_max,
                )
                rel = cut_time - window_start
                pick = _SalientCut(
                    time_s=cut_time,
                    magnitude=0.0,
                    reason=f"Cadence fill @ {rel:.2f}s",
                )
            if pick.time_s >= window_end - _MIN_SLOT_S:
                break
            repaired.append(round(pick.time_s, 6))
            repaired_cuts.append(pick)
            cursor = pick.time_s
        repaired.append(round(window_end, 6))
        boundaries, cuts = _clamp_boundary_count(
            repaired,
            repaired_cuts,
            lo=lo,
            hi=hi,
            window_start=window_start,
            beat_grid=beat_grid,
        )

    reasons = _slot_reasons_from_cuts(boundaries, cuts, window_start=window_start)
    return _BoundaryPlan(boundaries=boundaries, slot_reasons=reasons)


def _compute_boundaries(
    window_start: float,
    window_end: float,
    downbeats: list[float],
    target_slot_count: int,
    *,
    scope_lanes: dict[str, np.ndarray] | None = None,
    absolute_downbeats: list[float] | None = None,
) -> _BoundaryPlan:
    """Pick boundaries from salient audio events or fall back to even/downbeat splits."""
    duration = max(window_end - window_start, _MIN_SLOT_S)
    if target_slot_count <= 0:
        return _BoundaryPlan(
            boundaries=[window_start, window_end],
            slot_reasons=["Hook slot"],
        )

    slot_count = min(target_slot_count, max(1, int(duration / _MIN_SLOT_S)))
    abs_downbeats = absolute_downbeats if absolute_downbeats is not None else [
        window_start + t for t in downbeats
    ]

    if scope_lanes is not None:
        soft_range = _soft_count_range(duration, slot_count)
        return _salient_boundaries(
            window_start,
            window_end,
            downbeats=downbeats,
            scope_lanes=scope_lanes,
            absolute_downbeats=abs_downbeats,
            soft_count_range=soft_range,
        )

    energy_peaks = find_energy_peaks(
        scope_lanes,
        abs_downbeats,
        window_start_s=window_start,
        window_end_s=window_end,
    )
    peak_times = [peak.time_s for peak in energy_peaks]

    def _even_split(count: int) -> _BoundaryPlan:
        step = duration / count
        bounds = [round(window_start + step * index, 6) for index in range(count)]
        bounds.append(round(window_end, 6))
        reasons = _slot_reasons_from_cuts(bounds, [], window_start=window_start)
        return _BoundaryPlan(boundaries=bounds, slot_reasons=reasons)

    local_downbeats = [
        t for t in downbeats if window_start - 1e-6 <= t < window_end - 1e-6
    ]
    if len(local_downbeats) < 2 or slot_count == 1:
        return _even_split(slot_count)

    ideal = duration / slot_count
    boundaries = [window_start]
    cursor = window_start
    while len(boundaries) < slot_count and cursor < window_end - _MIN_SLOT_S - 1e-6:
        target = cursor + ideal
        candidates = [t for t in local_downbeats if t > cursor + _MIN_SLOT_S - 1e-6]
        if not candidates:
            break
        peak_candidates = [
            t for t in candidates
            if any(abs(t - pt) <= 0.25 for pt in peak_times)
        ]
        pick_from = peak_candidates if peak_candidates else candidates
        next_boundary = min(pick_from, key=lambda t: abs(t - target))
        if next_boundary >= window_end - _MIN_SLOT_S:
            break
        boundaries.append(next_boundary)
        cursor = next_boundary
    boundaries.append(round(window_end, 6))

    actual_slots = len(boundaries) - 1
    if actual_slots < slot_count:
        return _even_split(slot_count)
    if any(
        boundaries[index + 1] - boundaries[index] < _MIN_SLOT_S - 1e-6
        for index in range(slot_count)
    ):
        return _even_split(slot_count)
    trimmed = boundaries[: slot_count + 1]
    reasons = _slot_reasons_from_cuts(trimmed, [], window_start=window_start)
    return _BoundaryPlan(boundaries=trimmed, slot_reasons=reasons)


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


def hook_payoff_downbeats_s(
    hook_budget_s: float,
    features: BeatSyncFeatures | None,
    *,
    music_start_s: float,
    music_end_s: float,
) -> list[float]:
    """Valid hook-start durations on the music downbeat grid within hook budget."""
    if hook_budget_s <= 2 * _HOOK_MIN_PART_S:
        return [round(max(_HOOK_MIN_PART_S, hook_budget_s - _HOOK_MIN_PART_S), 6)]

    min_s = _HOOK_MIN_PART_S
    max_s = round(hook_budget_s - _HOOK_MIN_PART_S, 6)
    downbeats = _relative_downbeats(
        features,
        music_start_s=music_start_s,
        music_end_s=music_end_s,
    )
    if not downbeats or downbeats[0] > 1e-6:
        downbeats = [0.0, *downbeats]
    candidates = sorted({round(t, 6) for t in downbeats if min_s - 1e-6 <= t <= max_s + 1e-6})
    if candidates:
        return candidates
    fallback = round(min(max(hook_budget_s * 0.5, min_s), max_s), 6)
    return [fallback]


def snap_hook_payoff_s(
    requested_s: float,
    hook_budget_s: float,
    features: BeatSyncFeatures | None,
    *,
    music_start_s: float,
    music_end_s: float,
) -> float:
    """Snap a requested hook payoff to the nearest valid downbeat position."""
    positions = hook_payoff_downbeats_s(
        hook_budget_s,
        features,
        music_start_s=music_start_s,
        music_end_s=music_end_s,
    )
    if not positions:
        return round(requested_s, 6)
    clamped = max(
        _HOOK_MIN_PART_S,
        min(requested_s, hook_budget_s - _HOOK_MIN_PART_S),
    )
    return min(positions, key=lambda t: abs(t - clamped))


def _min_slot_duration_s(role: str) -> float:
    if role in ("hook_start", "hook_end"):
        return _HOOK_MIN_PART_S
    return _MIN_SLOT_S


def _place_timeline_slot(
    slot: StorySlot,
    *,
    start_s: float,
    end_s: float,
    target_duration_s: float | None = None,
) -> StorySlot:
    """Place a slot on the output timeline without stretching past its boundary."""
    if target_duration_s is not None:
        duration = round(target_duration_s, 6)
    else:
        duration = round(max(end_s - start_s, 1e-6), 6)
    return slot.model_copy(
        update={
            "out_start_s": round(start_s, 6),
            "out_end_s": round(end_s, 6),
            "target_duration_s": duration,
        }
    )


def _slot_from_boundary(
    slot: StorySlot,
    *,
    start_s: float,
    end_s: float,
) -> StorySlot:
    duration = round(max(end_s - start_s, 1e-6), 6)
    return slot.model_copy(
        update={
            "out_start_s": round(start_s, 6),
            "out_end_s": round(end_s, 6),
            "target_duration_s": duration,
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
        payoff_d = hook_start.target_duration_s
        build_d = hook_end.target_duration_s
        hook_budget = round(payoff_d + build_d, 6)
        max_payoff = max(hook_budget - _HOOK_MIN_PART_S, _HOOK_MIN_PART_S)
        payoff_end = _snap_time_to_downbeat(
            payoff_d,
            downbeats,
            min_s=_HOOK_MIN_PART_S,
            max_s=max_payoff,
        )
        build_d = round(hook_budget - payoff_end, 6)
        build_d = max(build_d, _HOOK_MIN_PART_S)
        payoff_end = round(hook_budget - build_d, 6)
        build_start = round(total_duration_s - build_d, 6)
        middle_min = payoff_end + _MIN_SLOT_S * max(len(middle), 1)
        if middle and build_start < middle_min:
            build_start = round(middle_min, 6)
            build_d = max(round(total_duration_s - build_start, 6), _HOOK_MIN_PART_S)
            payoff_end = max(round(hook_budget - build_d, 6), _HOOK_MIN_PART_S)
            build_d = round(hook_budget - payoff_end, 6)
            build_start = round(total_duration_s - build_d, 6)

        relaid = [
            _place_timeline_slot(
                hook_start,
                start_s=0.0,
                end_s=payoff_end,
                target_duration_s=payoff_end,
            ),
        ]
        if middle:
            span = build_start - payoff_end
            bounds = _compute_boundaries(
                payoff_end,
                build_start,
                downbeats,
                len(middle),
            ).boundaries
            bounds[0] = payoff_end
            bounds[-1] = build_start
            if any(bounds[i + 1] - bounds[i] < _MIN_SLOT_S - 1e-6 for i in range(len(middle))):
                step = span / len(middle)
                bounds = [
                    round(payoff_end + step * index, 6) for index in range(len(middle))
                ] + [round(build_start, 6)]
            for index, slot in enumerate(middle):
                relaid.append(
                    _place_timeline_slot(
                        slot,
                        start_s=bounds[index],
                        end_s=bounds[index + 1],
                    )
                )
        relaid.append(
            _place_timeline_slot(
                hook_end,
                start_s=build_start,
                end_s=total_duration_s,
                target_duration_s=build_d,
            )
        )
        return relaid

    if hook is not None:
        slot_count = 1 + len(middle)
        bounds = _compute_boundaries(0.0, total_duration_s, downbeats, slot_count).boundaries
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


def _hook_assigned_clip_id(
    hook: StorySlot | None,
    hook_start: StorySlot | None,
    hook_end: StorySlot | None,
) -> str | None:
    for slot in (hook, hook_start, hook_end):
        if slot is not None and slot.assigned_clip_id:
            return slot.assigned_clip_id
    return None


def _hook_source_range_for_split(
    *,
    hook_budget: float,
    hook: StorySlot | None,
    hook_start: StorySlot | None,
    hook_end: StorySlot | None,
    clip_media: dict[str, MediaInfo] | None = None,
) -> tuple[float, float]:
    """Contiguous hook source span for 1:1 payoff/build crop windows."""
    clip_id = _hook_assigned_clip_id(hook, hook_start, hook_end)

    if hook is not None:
        crop_start = hook.crop_start_s if hook.crop_start_s is not None else 0.0
        crop_end = (
            hook.crop_end_s
            if hook.crop_end_s is not None
            else crop_start + hook_budget
        )
    else:
        crop_start, crop_end = _full_hook_crop(hook_start, hook_end)
        if crop_end <= crop_start + 1e-6 and clip_id and clip_media and clip_id in clip_media:
            media = clip_media[clip_id]
            crop_start = 0.0
            crop_end = round(media.duration_s, 6)

    if clip_id and clip_media and clip_id in clip_media:
        media = clip_media[clip_id]
        crop_start = max(0.0, min(crop_start, media.duration_s))
        crop_end = max(crop_start + 1e-6, min(crop_end, media.duration_s))

    crop_span = max(crop_end - crop_start, 0.0)
    if crop_span <= 1e-6:
        if clip_id and clip_media and clip_id in clip_media:
            media = clip_media[clip_id]
            return 0.0, round(media.duration_s, 6)
        return 0.0, round(hook_budget, 6)

    return round(crop_start, 6), round(crop_end, 6)


def apply_hook_inversion_layout(
    storyboard: Storyboard,
    *,
    enabled: bool,
    payoff_duration_s: float,
    features: BeatSyncFeatures | None = None,
    scope_lanes: dict | None = None,
    clip_media: dict[str, MediaInfo] | None = None,
    reshape_crops: bool = True,
) -> Storyboard:
    """Split the hook into start/end storyboard slots aligned to the music block."""
    del scope_lanes
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

    if (
        hook is None
        and hook_start is not None
        and hook_end is not None
        and not reshape_crops
    ):
        hook_budget = hook_start.target_duration_s + hook_end.target_duration_s
        payoff_d = min(
            max(payoff_duration_s, _HOOK_MIN_PART_S),
            hook_budget - _HOOK_MIN_PART_S,
        )
        payoff_d = snap_hook_payoff_s(
            payoff_d,
            hook_budget,
            features,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
        )
        build_d = hook_budget - payoff_d
        start_slot = hook_start.model_copy(
            update={
                "target_duration_s": round(payoff_d, 6),
                "order": 0,
            }
        )
        end_slot = hook_end.model_copy(
            update={
                "target_duration_s": round(build_d, 6),
                "order": len(middle) + 1,
                "transition_in": middle[-1].transition_in if middle else hook_end.transition_in,
            }
        )
        reordered = [start_slot]
        for index, slot in enumerate(middle):
            reordered.append(slot.model_copy(update={"order": index + 1}))
        reordered.append(end_slot)
        relaid = relayout_beat_aligned_timeline(
            reordered,
            total_duration_s=storyboard.total_duration_s,
            features=features,
            music_start_s=storyboard.music_start_s,
            music_end_s=storyboard.music_end_s,
        )
        total = relaid[-1].out_end_s if relaid else storyboard.total_duration_s
        return storyboard.model_copy(update={"slots": relaid, "total_duration_s": total})

    base = hook or hook_start or hook_end
    assert base is not None
    root_id = base.id.replace("_hook_start", "").replace("_hook_end", "")
    if hook is not None:
        hook_budget = hook.target_duration_s
    else:
        hook_budget = (hook_start.target_duration_s if hook_start else 0.0) + (
            hook_end.target_duration_s if hook_end else 0.0
        )

    crop_start, crop_end = _hook_source_range_for_split(
        hook_budget=hook_budget,
        hook=hook,
        hook_start=hook_start,
        hook_end=hook_end,
        clip_media=clip_media,
    )

    payoff_d = min(
        max(payoff_duration_s, _HOOK_MIN_PART_S),
        hook_budget - _HOOK_MIN_PART_S,
    )
    payoff_d = snap_hook_payoff_s(
        payoff_d,
        hook_budget,
        features,
        music_start_s=storyboard.music_start_s,
        music_end_s=storyboard.music_end_s,
    )
    build_d = hook_budget - payoff_d
    head, tail = split_hook_crop_by_output_ratio(
        crop_start, crop_end, payoff_d, build_d
    )

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


def slot_at_storyboard_time(storyboard: Storyboard, time_s: float) -> StorySlot | None:
    """Return the storyboard slot whose output window contains ``time_s``."""
    ordered = sorted(storyboard.slots, key=lambda item: item.order)
    for slot in ordered:
        if slot.out_start_s <= time_s + 1e-6 and time_s < slot.out_end_s - 1e-6:
            return slot
    if ordered and time_s >= ordered[-1].out_start_s - 1e-6:
        return ordered[-1]
    return None


def _composite_video_start_for_assigned_index(
    assigned: list[StorySlot],
    index: int,
    *,
    xfade_s: float = _DEFAULT_XFADE_S,
) -> float:
    video_start = 0.0
    for i in range(index):
        video_start += assigned[i].target_duration_s
        if i + 1 < len(assigned) and assigned[i + 1].transition_in == "xfade":
            video_start -= xfade_s
    return video_start


def storyboard_time_to_composite_time(
    storyboard: Storyboard,
    time_s: float,
    *,
    xfade_s: float = _DEFAULT_XFADE_S,
) -> float | None:
    """Map block playhead time to packed composited preview video time."""
    assigned = assigned_storyboard_slots(storyboard)
    if not assigned:
        return None

    for index, slot in enumerate(assigned):
        in_slot = time_s >= slot.out_start_s - 1e-6 and (
            time_s < slot.out_end_s - 1e-6 or index == len(assigned) - 1
        )
        if not in_slot:
            continue
        slot_span = slot.out_end_s - slot.out_start_s
        ratio = (
            max(0.0, min(1.0, (time_s - slot.out_start_s) / slot_span))
            if slot_span > 1e-9
            else 0.0
        )
        video_start = _composite_video_start_for_assigned_index(
            assigned,
            index,
            xfade_s=xfade_s,
        )
        return video_start + ratio * slot.target_duration_s

    return None


def remap_fx_events_for_composite(
    fx_events: list[FxEvent],
    storyboard: Storyboard,
    *,
    xfade_s: float = _DEFAULT_XFADE_S,
) -> list[FxEvent]:
    """Keep FX only for assigned slots; remap timestamps to packed composite time."""
    remapped: list[FxEvent] = []
    for event in fx_events:
        slot = slot_at_storyboard_time(storyboard, event.timestamp_s)
        if slot is None or not slot.assigned_clip_id:
            continue
        composite_t = storyboard_time_to_composite_time(
            storyboard,
            event.timestamp_s,
            xfade_s=xfade_s,
        )
        if composite_t is None:
            continue
        remapped.append(
            event.model_copy(update={"timestamp_s": round(composite_t, 6)})
        )
    return remapped


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
