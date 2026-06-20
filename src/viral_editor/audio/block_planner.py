"""Suggest retention-friendly music windows from audio analysis.

Legacy envelope/chroma planner — production pipeline uses ``loop_planner`` when
``features.npz`` is available (see ``api.music.suggest_blocks_from_artifacts``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from viral_editor.editing.retention_policy import retention_bonus_for_window
from viral_editor.models import AudioTimeline, MusicBlock, MusicBlockPlan, Transient

DEFAULT_HOP_LENGTH = 512
DEFAULT_SR = 22050
BEATS_PER_BAR = 4
LOOP_MAX_DRIFT_RATIO = 0.28
LOOP_SEAM_WINDOW_S = 0.06
LOOP_CROSSFADE_S = 0.05


@dataclass(frozen=True)
class _Candidate:
    start_s: float
    end_s: float
    score: float
    drop_count: int
    transient_count: int
    label: str
    reason: str
    loop_seam_score: float = 0.0


def _envelope_time(index: int, *, hop_length: int, sr: int) -> float:
    return index * hop_length / sr


def _time_to_index(time_s: float, *, hop_length: int, sr: int) -> int:
    return int(round(time_s * sr / hop_length))


def _format_timestamp(time_s: float) -> str:
    minutes = int(time_s // 60)
    seconds = int(time_s % 60)
    return f"{minutes}:{seconds:02d}"


def _beat_period(bpm: float) -> float:
    return 60.0 / bpm


def _bar_period(bpm: float, *, beats_per_bar: int = BEATS_PER_BAR) -> float:
    return _beat_period(bpm) * beats_per_bar


def _sample_envelope(
    onset_envelope: np.ndarray,
    time_s: float,
    *,
    hop_length: int,
    sr: int,
) -> float:
    if onset_envelope.size == 0:
        return 0.0
    index = _time_to_index(time_s, hop_length=hop_length, sr=sr)
    index = max(0, min(index, onset_envelope.size - 1))
    peak = float(onset_envelope.max())
    if peak <= 0:
        return 0.0
    return float(onset_envelope[index] / peak)


def _envelope_slice(
    onset_envelope: np.ndarray,
    start_s: float,
    end_s: float,
    *,
    hop_length: int,
    sr: int,
) -> np.ndarray:
    start_idx = max(0, _time_to_index(start_s, hop_length=hop_length, sr=sr))
    end_idx = min(len(onset_envelope), _time_to_index(end_s, hop_length=hop_length, sr=sr))
    if end_idx <= start_idx:
        return np.array([], dtype=float)
    segment = onset_envelope[start_idx:end_idx].astype(float)
    peak = float(segment.max()) if segment.size else 0.0
    if peak <= 0:
        peak = float(onset_envelope.max()) if onset_envelope.size else 1.0
    if peak <= 0:
        return segment
    return segment / peak


def _chroma_slice(
    chroma: np.ndarray,
    start_s: float,
    end_s: float,
    *,
    hop_length: int,
    sr: int,
) -> np.ndarray:
    start_idx = max(0, _time_to_index(start_s, hop_length=hop_length, sr=sr))
    end_idx = min(chroma.shape[1], _time_to_index(end_s, hop_length=hop_length, sr=sr))
    if end_idx <= start_idx:
        return np.empty((chroma.shape[0], 0), dtype=float)
    return chroma[:, start_idx:end_idx]


def _correlation_score(left: np.ndarray, right: np.ndarray) -> float:
    length = min(left.size, right.size)
    if length < 4:
        return 0.0
    a = np.asarray(left[:length], dtype=float).reshape(-1)
    b = np.asarray(right[:length], dtype=float).reshape(-1)
    a = a - a.mean()
    b = b - b.mean()
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom <= 1e-9:
        return 0.0
    pearson = float(np.dot(a, b) / denom)
    return max(0.0, min(1.0, (pearson + 1.0) / 2.0))


def _transient_phase_match(
    start_s: float,
    end_s: float,
    transients: list[Transient],
    *,
    bar_s: float,
) -> float:
    """Compare hit placement within a bar at the in-point vs out-point."""
    if bar_s <= 0:
        return 0.0

    def bar_profile(anchor_s: float) -> np.ndarray:
        bins = np.zeros(8, dtype=float)
        for transient in transients:
            time_s = transient.timestamp_ms / 1000.0
            if anchor_s - 0.02 <= time_s < anchor_s + bar_s:
                phase = (time_s - anchor_s) / bar_s
                index = min(int(phase * 8), 7)
                weight = 1.0 if transient.type == "drop" else 0.65
                bins[index] += weight
        total = float(bins.sum())
        if total <= 0:
            return bins
        return bins / total

    head = bar_profile(start_s)
    tail = bar_profile(end_s - bar_s)
    if head.sum() <= 0 or tail.sum() <= 0:
        return 0.0
    return _correlation_score(head, tail)


def _loop_repeat_score(
    start_s: float,
    end_s: float,
    onset_envelope: np.ndarray,
    chroma: np.ndarray | None,
    *,
    bpm: float,
    transients: list[Transient],
    hop_length: int,
    sr: int,
) -> float:
    """Score how well the tail repeats the head for a seamless loop."""
    if end_s <= start_s:
        return 0.0

    bar = _bar_period(bpm)
    weighted: list[tuple[float, float]] = []

    for n_bars in (1, 2, 4):
        pattern_s = n_bars * bar
        if end_s - start_s < pattern_s * 1.35:
            continue
        head_env = _envelope_slice(
            onset_envelope,
            start_s,
            start_s + pattern_s,
            hop_length=hop_length,
            sr=sr,
        )
        tail_env = _envelope_slice(
            onset_envelope,
            end_s - pattern_s,
            end_s,
            hop_length=hop_length,
            sr=sr,
        )
        env_weight = 0.18 + 0.08 * n_bars
        weighted.append((env_weight, _correlation_score(head_env, tail_env)))

        if chroma is not None and chroma.size > 0:
            head_chroma = _chroma_slice(
                chroma, start_s, start_s + pattern_s, hop_length=hop_length, sr=sr
            )
            tail_chroma = _chroma_slice(
                chroma, end_s - pattern_s, end_s, hop_length=hop_length, sr=sr
            )
            if head_chroma.shape[1] >= 3 and tail_chroma.shape[1] >= 3:
                chroma_weight = 0.22 + 0.1 * n_bars
                weighted.append(
                    (
                        chroma_weight,
                        _correlation_score(head_chroma.flatten(), tail_chroma.flatten()),
                    )
                )

    weighted.append(
        (
            0.16,
            _transient_phase_match(start_s, end_s, transients, bar_s=bar),
        )
    )
    weighted.append(
        (
            0.06,
            _loop_boundary_score(start_s, end_s, onset_envelope, hop_length=hop_length, sr=sr),
        )
    )

    total = sum(weight for weight, _ in weighted)
    if total <= 0:
        return 0.0
    return sum(weight * score for weight, score in weighted) / total


def _loop_boundary_score(
    start_s: float,
    end_s: float,
    onset_envelope: np.ndarray,
    *,
    hop_length: int,
    sr: int,
) -> float:
    """Legacy point match — small weight in the combined repeat score."""
    inset = LOOP_SEAM_WINDOW_S
    start_sample = _sample_envelope(
        onset_envelope, start_s, hop_length=hop_length, sr=sr
    )
    end_sample = _sample_envelope(
        onset_envelope, max(start_s, end_s - inset), hop_length=hop_length, sr=sr
    )
    start_mean = _mean_envelope(
        onset_envelope, start_s, start_s + inset, hop_length=hop_length, sr=sr
    )
    end_mean = _mean_envelope(
        onset_envelope,
        max(start_s, end_s - inset),
        end_s,
        hop_length=hop_length,
        sr=sr,
    )
    delta = abs(start_sample - end_sample) + abs(start_mean - end_mean)
    return max(0.0, min(1.0, 1.0 - delta * 1.25))


def _loop_seam_score(
    start_s: float,
    end_s: float,
    onset_envelope: np.ndarray,
    *,
    hop_length: int,
    sr: int,
) -> float:
    """Backward-compatible alias for boundary-only scoring."""
    return _loop_boundary_score(
        start_s, end_s, onset_envelope, hop_length=hop_length, sr=sr
    )


def _snap_start_for_loop(
    start_s: float,
    *,
    bpm: float,
    transients: list[Transient],
) -> float:
    """Pick a bar-phase-aligned start near ``start_s``, preferring on-grid hits."""
    bar = _bar_period(bpm)
    candidates: set[float] = {start_s}
    bar_index = round(start_s / bar)
    for delta in (-2, -1, 0, 1, 2):
        candidates.add(max(0.0, (bar_index + delta) * bar))
    for transient in transients:
        time_s = transient.timestamp_ms / 1000.0
        if abs(time_s - start_s) <= 0.35:
            candidates.add(time_s)

    best = start_s
    best_score = -1.0
    for candidate in candidates:
        phase = candidate % bar
        phase_dist = min(phase, bar - phase)
        phase_score = 1.0 - (phase_dist / (bar / 2.0))
        on_hit = any(
            abs(transient.timestamp_ms / 1000.0 - candidate) <= 0.06
            for transient in transients
        )
        proximity = 1.0 - min(abs(candidate - start_s) / 0.5, 1.0)
        score = phase_score * 0.55 + proximity * 0.25 + (0.2 if on_hit else 0.0)
        if score > best_score:
            best_score = score
            best = candidate
    return best


def _refine_loop_end(
    start_s: float,
    end_s: float,
    *,
    target_duration_s: float,
    track_duration: float,
    bpm: float,
    transients: list[Transient],
    onset_envelope: np.ndarray,
    chroma: np.ndarray | None,
    hop_length: int,
    sr: int,
    max_drift_ratio: float,
) -> tuple[float, float]:
    """Nudge the out-point by fractions of a beat to maximize repeat match."""
    beat = _beat_period(bpm)
    min_dur = target_duration_s * (1.0 - max_drift_ratio)
    max_dur = target_duration_s * (1.0 + max_drift_ratio)

    best_end = end_s
    best_score = _loop_repeat_score(
        start_s,
        end_s,
        onset_envelope,
        chroma,
        bpm=bpm,
        transients=transients,
        hop_length=hop_length,
        sr=sr,
    )

    for delta in (-2 * beat, -beat, -beat / 2, beat / 2, beat, 2 * beat):
        candidate = end_s + delta
        duration = candidate - start_s
        if duration < min_dur - 1e-6 or duration > max_dur + 1e-6:
            continue
        if candidate > track_duration + 1e-6:
            continue
        score = _loop_repeat_score(
            start_s,
            candidate,
            onset_envelope,
            chroma,
            bpm=bpm,
            transients=transients,
            hop_length=hop_length,
            sr=sr,
        )
        if score > best_score:
            best_score = score
            best_end = candidate
    return best_end, best_score


def _find_loop_aligned_end(
    start_s: float,
    *,
    target_duration_s: float,
    track_duration: float,
    bpm: float,
    transients: list[Transient],
    onset_envelope: np.ndarray,
    chroma: np.ndarray | None,
    hop_length: int,
    sr: int,
    max_drift_ratio: float = LOOP_MAX_DRIFT_RATIO,
) -> tuple[float, float]:
    """Return ``(end_s, repeat_score)`` where the tail best matches the head."""
    bar = _bar_period(bpm)
    min_dur = target_duration_s * (1.0 - max_drift_ratio)
    max_dur = target_duration_s * (1.0 + max_drift_ratio)

    best_end = min(start_s + target_duration_s, track_duration)
    best_score = -1.0

    n_bars_min = max(1, int(min_dur / bar - 0.01))
    n_bars_max = int(max_dur / bar + 0.99) + 1
    for n_bars in range(n_bars_min, n_bars_max + 1):
        end_s = start_s + n_bars * bar
        if end_s > track_duration + 1e-6:
            continue
        duration = end_s - start_s
        if duration < min_dur - 1e-6 or duration > max_dur + 1e-6:
            continue
        repeat = _loop_repeat_score(
            start_s,
            end_s,
            onset_envelope,
            chroma,
            bpm=bpm,
            transients=transients,
            hop_length=hop_length,
            sr=sr,
        )
        drift_penalty = abs(duration - target_duration_s) / target_duration_s
        combined = repeat - drift_penalty * 0.08
        if combined > best_score:
            best_score = combined
            best_end = end_s

    if best_score < 0:
        beat = _beat_period(bpm)
        n_beats_min = max(BEATS_PER_BAR, int(min_dur / beat - 0.01))
        n_beats_max = int(max_dur / beat + 0.99) + 1
        for n_beats in range(n_beats_min, n_beats_max + 1):
            end_s = start_s + n_beats * beat
            if end_s > track_duration + 1e-6:
                continue
            duration = end_s - start_s
            if duration < min_dur - 1e-6 or duration > max_dur + 1e-6:
                continue
            repeat = _loop_repeat_score(
                start_s,
                end_s,
                onset_envelope,
                chroma,
                bpm=bpm,
                transients=transients,
                hop_length=hop_length,
                sr=sr,
            )
            drift_penalty = abs(duration - target_duration_s) / target_duration_s
            combined = repeat - drift_penalty * 0.08
            if combined > best_score:
                best_score = combined
                best_end = end_s

    if best_score < 0:
        fallback_end = min(start_s + target_duration_s, track_duration)
        best_end = _snap_end_to_transient(
            fallback_end,
            start_s,
            transients,
            min_duration_s=min_dur,
        )
        repeat = _loop_repeat_score(
            start_s,
            best_end,
            onset_envelope,
            chroma,
            bpm=bpm,
            transients=transients,
            hop_length=hop_length,
            sr=sr,
        )
        return best_end, repeat

    refined_end, refined_score = _refine_loop_end(
        start_s,
        best_end,
        target_duration_s=target_duration_s,
        track_duration=track_duration,
        bpm=bpm,
        transients=transients,
        onset_envelope=onset_envelope,
        chroma=chroma,
        hop_length=hop_length,
        sr=sr,
        max_drift_ratio=max_drift_ratio,
    )
    return refined_end, refined_score


def _loop_reason_suffix(
    *,
    start_s: float,
    end_s: float,
    target_duration_s: float,
    bpm: float,
    seam_score: float,
) -> str:
    duration = end_s - start_s
    bar = _bar_period(bpm)
    bars = duration / bar
    bars_round = round(bars)
    if abs(bars - bars_round) < 0.08 and bars_round >= 1:
        grid = f"{int(bars_round)}-bar loop"
    else:
        grid = "beat-aligned loop"
    drift = duration - target_duration_s
    drift_note = ""
    if abs(drift) >= 0.35:
        drift_note = f", {duration:.1f}s (target {target_duration_s:.0f}s)"
    elif abs(drift) >= 0.05:
        drift_note = f", {duration:.1f}s"
    quality = "seamless" if seam_score >= 0.78 else "smooth" if seam_score >= 0.62 else "aligned"
    return f" · {quality} repeat {grid}{drift_note}"


def _snap_start_to_transient(start_s: float, transients: list[Transient]) -> float:
    """Snap window start to a nearby hit, preferring clean non-drop cut points."""
    if not transients:
        return start_s
    nearby = [
        t
        for t in transients
        if abs(t.timestamp_ms / 1000.0 - start_s) <= 0.25
    ]
    if not nearby:
        return start_s
    non_drops = [t for t in nearby if t.type != "drop"]
    pick_from = non_drops if non_drops else nearby
    chosen = min(pick_from, key=lambda t: abs(t.timestamp_ms / 1000.0 - start_s))
    return chosen.timestamp_ms / 1000.0


def _snap_end_to_transient(
    end_s: float,
    start_s: float,
    transients: list[Transient],
    *,
    min_duration_s: float,
) -> float:
    """Snap window end to a nearby hit so preview loops land on a beat."""
    if not transients:
        return end_s
    nearby = [
        t
        for t in transients
        if abs(t.timestamp_ms / 1000.0 - end_s) <= 0.25
        and (t.timestamp_ms / 1000.0 - start_s) >= min_duration_s * 0.9
    ]
    if not nearby:
        return end_s
    non_drops = [t for t in nearby if t.type != "drop"]
    pick_from = non_drops if non_drops else nearby
    chosen = min(pick_from, key=lambda t: abs(t.timestamp_ms / 1000.0 - end_s))
    return chosen.timestamp_ms / 1000.0


def _first_drop_offset_s(drops: list[Transient], start_s: float) -> float | None:
    offsets = [t.timestamp_ms / 1000.0 - start_s for t in drops]
    in_window = [offset for offset in offsets if offset >= -0.05]
    if not in_window:
        return None
    return min(in_window)


def _classify_window(
    *,
    start_s: float,
    end_s: float,
    drop_count: int,
    drops: list[Transient],
    energy: float,
) -> tuple[str, str]:
    window_dur = end_s - start_s
    first_drop = _first_drop_offset_s(drops, start_s)
    range_label = f"{_format_timestamp(start_s)}–{_format_timestamp(end_s)}"

    if drop_count >= 3:
        return (
            "Drop cluster",
            f"{drop_count} drops across {range_label}",
        )
    if drop_count >= 2:
        return (
            "Peak section",
            f"Two drops in {range_label} — stacked energy",
        )
    if first_drop is not None and first_drop <= 0.25:
        return (
            "Drop opener",
            f"Opens on drop at {_format_timestamp(start_s + first_drop)}",
        )
    if first_drop is not None and first_drop <= window_dur * 0.4:
        return (
            "Quick build",
            f"Drop at {_format_timestamp(start_s + first_drop)} after a short ramp",
        )
    if first_drop is not None and first_drop >= window_dur * 0.65:
        return (
            "Late payoff",
            f"Drop at {_format_timestamp(start_s + first_drop)} near the out-point",
        )
    if first_drop is not None:
        return (
            "Build + hit",
            f"Drop at {_format_timestamp(start_s + first_drop)} mid-window",
        )
    if energy >= 0.55:
        return (
            "High energy",
            f"Dense hits across {range_label}",
        )
    return (
        "Steady groove",
        f"Even rhythm across {range_label}",
    )


def _transients_in_window(
    transients: list[Transient],
    start_s: float,
    end_s: float,
) -> list[Transient]:
    return [t for t in transients if start_s <= (t.timestamp_ms / 1000.0) < end_s]


def _mean_envelope(
    onset_envelope: np.ndarray,
    start_s: float,
    end_s: float,
    *,
    hop_length: int,
    sr: int,
) -> float:
    start_idx = max(0, _time_to_index(start_s, hop_length=hop_length, sr=sr))
    end_idx = min(len(onset_envelope), _time_to_index(end_s, hop_length=hop_length, sr=sr))
    if end_idx <= start_idx:
        return 0.0
    segment = onset_envelope[start_idx:end_idx]
    if segment.size == 0:
        return 0.0
    peak = float(onset_envelope.max()) if onset_envelope.size else 1.0
    if peak <= 0:
        return 0.0
    return float(segment.mean() / peak)


def _synthetic_downbeats(start_s: float, end_s: float, *, bpm: float) -> list[float]:
    bar_period = (60.0 / bpm) * BEATS_PER_BAR
    if bar_period <= 1e-9:
        return []
    times: list[float] = []
    cursor = start_s
    while cursor < end_s - 1e-6:
        times.append(cursor)
        cursor += bar_period
    return times


def _score_window(
    start_s: float,
    end_s: float,
    *,
    target_duration_s: float,
    timeline: AudioTimeline,
    onset_envelope: np.ndarray,
    chroma: np.ndarray | None,
    hop_length: int,
    sr: int,
    scope_lanes: dict[str, np.ndarray] | None = None,
) -> _Candidate:
    window_transients = _transients_in_window(timeline.transients, start_s, end_s)
    drops = [t for t in window_transients if t.type == "drop"]
    drop_count = len(drops)

    energy = _mean_envelope(
        onset_envelope, start_s, end_s, hop_length=hop_length, sr=sr
    )

    drop_near_start = any(
        abs(t.timestamp_ms / 1000.0 - start_s) <= 0.25 for t in drops
    )
    drop_soon_after = any(
        0.25 < (t.timestamp_ms / 1000.0 - start_s) <= 2.0 for t in drops
    )
    drop_bonus = 0.25 if drop_near_start else (0.1 if drop_soon_after else 0.0)
    drop_density = min(drop_count / 3.0, 1.0) * 0.35
    energy_score = energy * 0.4

    score = min(1.0, energy_score + drop_density + drop_bonus)
    if scope_lanes:
        downbeats = _synthetic_downbeats(start_s, end_s, bpm=timeline.global_bpm)
        score = min(
            1.0,
            score + retention_bonus_for_window(
                scope_lanes,
                downbeats,
                window_start_s=start_s,
                window_end_s=end_s,
            )
            * 0.15,
        )

    label, reason = _classify_window(
        start_s=start_s,
        end_s=end_s,
        drop_count=drop_count,
        drops=drops,
        energy=energy,
    )

    seam = _loop_repeat_score(
        start_s,
        end_s,
        onset_envelope,
        chroma,
        bpm=timeline.global_bpm,
        transients=timeline.transients,
        hop_length=hop_length,
        sr=sr,
    )
    score = min(1.0, score * 0.55 + seam * 0.45)
    reason = reason + _loop_reason_suffix(
        start_s=start_s,
        end_s=end_s,
        target_duration_s=target_duration_s,
        bpm=timeline.global_bpm,
        seam_score=seam,
    )

    return _Candidate(
        start_s=start_s,
        end_s=end_s,
        score=round(score, 4),
        drop_count=drop_count,
        transient_count=len(window_transients),
        label=label,
        reason=reason,
        loop_seam_score=round(seam, 4),
    )


def _non_maximum_suppress(
    candidates: list[_Candidate],
    *,
    min_gap_s: float,
    max_blocks: int,
) -> list[_Candidate]:
    ordered = sorted(candidates, key=lambda item: item.score, reverse=True)
    kept: list[_Candidate] = []
    for candidate in ordered:
        if all(
            abs(candidate.start_s - other.start_s) >= min_gap_s
            and abs(candidate.end_s - other.end_s) >= min_gap_s * 0.5
            for other in kept
        ):
            kept.append(candidate)
        if len(kept) >= max_blocks:
            break
    return sorted(kept, key=lambda item: item.start_s)


def _full_track_plan(
    timeline: AudioTimeline,
    *,
    target_duration_s: float,
) -> MusicBlockPlan:
    duration = timeline.audio_duration_seconds
    drops = sum(1 for t in timeline.transients if t.type == "drop")
    block = MusicBlock(
        id="block_full",
        start_s=0.0,
        end_s=duration,
        duration_s=duration,
        score=1.0,
        drop_count=drops,
        transient_count=len(timeline.transients),
        label="Full track",
        reason="Track is already shorter than the target short length",
    )
    return MusicBlockPlan(
        target_duration_s=target_duration_s,
        track_duration_s=duration,
        selected_block_id=block.id,
        use_full_track=True,
        blocks=[block],
    )


def suggest_music_blocks(
    timeline: AudioTimeline,
    onset_envelope: np.ndarray,
    *,
    chroma: np.ndarray | None = None,
    target_duration_s: float = 30.0,
    max_blocks: int = 5,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
    selected_block_id: str | None = None,
    scope_lanes: dict[str, np.ndarray] | None = None,
) -> MusicBlockPlan:
    """Rank sliding windows for a target short duration."""
    track_duration = timeline.audio_duration_seconds
    if track_duration <= target_duration_s:
        return _full_track_plan(timeline, target_duration_s=target_duration_s)

    beat_period = 60.0 / timeline.global_bpm
    step_s = max(beat_period / 2.0, 0.05)
    window_s = target_duration_s
    min_window_s = window_s * (1.0 - LOOP_MAX_DRIFT_RATIO)

    candidates: list[_Candidate] = []
    start = 0.0
    while start + min_window_s <= track_duration + 1e-6:
        snapped = _snap_start_for_loop(
            start,
            bpm=timeline.global_bpm,
            transients=timeline.transients,
        )
        end, _seam = _find_loop_aligned_end(
            snapped,
            target_duration_s=window_s,
            track_duration=track_duration,
            bpm=timeline.global_bpm,
            transients=timeline.transients,
            onset_envelope=onset_envelope,
            chroma=chroma,
            hop_length=hop_length,
            sr=sr,
        )
        if end - snapped >= min_window_s * 0.95:
            candidates.append(
                _score_window(
                    snapped,
                    end,
                    target_duration_s=window_s,
                    timeline=timeline,
                    onset_envelope=onset_envelope,
                    chroma=chroma,
                    hop_length=hop_length,
                    sr=sr,
                    scope_lanes=scope_lanes,
                )
            )
        start += step_s

    if not candidates:
        snapped = _snap_start_for_loop(
            0.0,
            bpm=timeline.global_bpm,
            transients=timeline.transients,
        )
        end, _seam = _find_loop_aligned_end(
            snapped,
            target_duration_s=min(window_s, track_duration - snapped),
            track_duration=track_duration,
            bpm=timeline.global_bpm,
            transients=timeline.transients,
            onset_envelope=onset_envelope,
            chroma=chroma,
            hop_length=hop_length,
            sr=sr,
            max_drift_ratio=max(LOOP_MAX_DRIFT_RATIO, 0.5),
        )
        if end <= snapped:
            end = min(snapped + window_s, track_duration)
        candidates.append(
            _score_window(
                snapped,
                end,
                target_duration_s=window_s,
                timeline=timeline,
                onset_envelope=onset_envelope,
                chroma=chroma,
                hop_length=hop_length,
                sr=sr,
                scope_lanes=scope_lanes,
            )
        )

    picked = _non_maximum_suppress(
        candidates,
        min_gap_s=window_s * 0.5,
        max_blocks=max_blocks,
    )

    blocks = [
        MusicBlock(
            id=f"block_{chr(ord('a') + index)}",
            start_s=round(item.start_s, 3),
            end_s=round(item.end_s, 3),
            duration_s=round(item.end_s - item.start_s, 3),
            score=item.score,
            drop_count=item.drop_count,
            transient_count=item.transient_count,
            label=item.label,
            reason=item.reason,
        )
        for index, item in enumerate(picked)
    ]

    auto_selected = selected_block_id
    if auto_selected is None and blocks:
        auto_selected = blocks[0].id
    if auto_selected and not any(block.id == auto_selected for block in blocks):
        auto_selected = blocks[0].id if blocks else None

    return MusicBlockPlan(
        target_duration_s=target_duration_s,
        track_duration_s=track_duration,
        selected_block_id=auto_selected,
        use_full_track=False,
        blocks=blocks,
    )


def apply_block_selection(
    plan: MusicBlockPlan,
    block_id: str,
) -> MusicBlockPlan:
    """Return a copy of the plan with ``selected_block_id`` updated."""
    if not any(block.id == block_id for block in plan.blocks):
        raise ValueError(f"Unknown block id: {block_id}")
    return plan.model_copy(update={"selected_block_id": block_id})


def selected_block(plan: MusicBlockPlan) -> MusicBlock | None:
    if plan.selected_block_id is None:
        return plan.blocks[0] if plan.blocks else None
    for block in plan.blocks:
        if block.id == plan.selected_block_id:
            return block
    return plan.blocks[0] if plan.blocks else None


def trim_timeline_to_window(
    timeline: AudioTimeline,
    *,
    start_s: float,
    end_s: float,
) -> AudioTimeline:
    """Filter and re-base transients to a music window."""
    trimmed: list[Transient] = []
    for transient in timeline.transients:
        time_s = transient.timestamp_ms / 1000.0
        if start_s <= time_s < end_s:
            trimmed.append(
                transient.model_copy(
                    update={"timestamp_ms": int(round((time_s - start_s) * 1000.0))}
                )
            )
    return timeline.model_copy(
        update={
            "audio_duration_seconds": round(end_s - start_s, 4),
            "transients": trimmed,
        }
    )
