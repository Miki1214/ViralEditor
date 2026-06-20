"""Sophisticated loop and section-aware music block planner."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import os

import numpy as np

from viral_editor.audio.features import BeatSyncFeatures

from viral_editor.editing.retention_policy import (
    pacing_density_score,
    retention_bonus_for_window,
    vocal_boundary_penalty,
)
from viral_editor.models import (
    AudioTimeline,
    MusicBlock,
    MusicBlockCatalog,
    MusicBlockPlan,
    MusicSection,
    TargetLoopQuality,
    Transient,
)

BEATS_PER_BAR = 4
LOOP_MAX_DRIFT_RATIO = 0.28
PHRASE_BAR_OPTIONS = (4, 8, 16)
CANONICAL_TARGET_DURATIONS_S = (5, 10, 15, 20, 25, 30, 45, 60)
# Longest short-form window we score during catalog precompute (60s chip + headroom).
CATALOG_MAX_WINDOW_S = 75.0
CATALOG_POLICY_RESCORE_TOP_N = 60
VOCAL_SEAM_WEIGHT = 0.5


def target_duration_bounds(target_duration_s: float) -> tuple[float, float]:
    """Return the half-open duration window ``[min_s, max_s)`` for a preset target.

    Each chip length owns a non-overlapping bucket so adjacent presets (e.g. 20s
    vs 25s) cannot pick the same phrase loop.
    """
    target = float(target_duration_s)
    presets = CANONICAL_TARGET_DURATIONS_S

    for index, preset in enumerate(presets):
        if abs(preset - target) < 1e-6:
            max_s = float(presets[index + 1]) if index + 1 < len(presets) else float("inf")
            return float(preset), max_s

    for index in range(len(presets) - 1, -1, -1):
        if target >= presets[index] - 1e-6:
            max_s = float(presets[index + 1]) if index + 1 < len(presets) else float("inf")
            return float(presets[index]), max_s

    return float(presets[0]), float(presets[1])


def _duration_in_target_window(duration_s: float, target_duration_s: float) -> bool:
    min_dur, max_dur = target_duration_bounds(target_duration_s)
    if duration_s + 1e-6 < min_dur:
        return False
    if max_dur == float("inf"):
        return True
    return duration_s < max_dur - 1e-6


@dataclass(frozen=True)
class _Candidate:
    start_s: float
    end_s: float
    start_beat: int
    end_beat: int
    phrase_bars: int
    retention: float
    loop_quality: float
    section_label: str | None
    is_repeated_section: bool
    drop_count: int
    transient_count: int
    label: str
    reason: str
    vocal_penalty: float = 0.0


def _format_timestamp(time_s: float) -> str:
    minutes = int(time_s // 60)
    seconds = int(time_s % 60)
    return f"{minutes}:{seconds:02d}"


def _beat_index(beat_times: np.ndarray, time_s: float) -> int:
    if beat_times.size == 0:
        return 0
    return int(np.argmin(np.abs(beat_times - time_s)))


def _correlation(a: np.ndarray, b: np.ndarray) -> float:
    n = min(a.size, b.size)
    if n < 4:
        return 0.0
    x = a[:n].astype(float).reshape(-1)
    y = b[:n].astype(float).reshape(-1)
    x = x - x.mean()
    y = y - y.mean()
    denom = float(np.linalg.norm(x) * np.linalg.norm(y))
    if denom <= 1e-9:
        return 1.0 if np.allclose(a, b, atol=1e-6) else 0.0
    r = float(np.dot(x, y) / denom)
    return max(0.0, min(1.0, (r + 1.0) / 2.0))


def _loop_quality(
    start_beat: int,
    end_beat: int,
    features: BeatSyncFeatures,
) -> float:
    n_beats = end_beat - start_beat
    if n_beats < BEATS_PER_BAR:
        return 0.0
    scores: list[float] = []
    for phrase_beats in (BEATS_PER_BAR, BEATS_PER_BAR * 2, BEATS_PER_BAR * 4):
        if n_beats < phrase_beats * 1.2:
            continue
        head = slice(start_beat, start_beat + phrase_beats)
        tail = slice(end_beat - phrase_beats, end_beat)
        scores.append(_correlation(features.chroma_sync[:, head].flatten(), features.chroma_sync[:, tail].flatten()))
        scores.append(_correlation(features.mfcc_sync[:, head].flatten(), features.mfcc_sync[:, tail].flatten()))
        scores.append(_correlation(features.rms_sync[:, head].flatten(), features.rms_sync[:, tail].flatten()))
        scores.append(_correlation(features.tonnetz_sync[:, head].flatten(), features.tonnetz_sync[:, tail].flatten()))
    if not scores:
        return 0.0
    return float(np.mean(scores))


def _transients_in_window(transients: list[Transient], start_s: float, end_s: float) -> list[Transient]:
    return [t for t in transients if start_s <= t.timestamp_ms / 1000.0 < end_s]


def _section_for_window(sections: list[MusicSection], start_s: float, end_s: float) -> MusicSection | None:
    best: MusicSection | None = None
    best_overlap = 0.0
    for section in sections:
        overlap = min(end_s, section.end_s) - max(start_s, section.start_s)
        if overlap > best_overlap:
            best_overlap = overlap
            best = section
    return best


def _classify_candidate(
    *,
    start_s: float,
    end_s: float,
    phrase_bars: int,
    drops: list[Transient],
    section: MusicSection | None,
    loop_quality: float,
    key: str,
    vocal_penalty: float = 0.0,
) -> tuple[str, str]:
    range_label = f"{_format_timestamp(start_s)}–{_format_timestamp(end_s)}"
    if section and section.is_repeated:
        label = section.label
        reason = f"{range_label} · {phrase_bars}-bar phrase in repeating {section.label.lower()}"
    elif drops and (drops[0].timestamp_ms / 1000.0 - start_s) <= 0.35:
        label = "Drop opener"
        reason = f"Opens on drop · {phrase_bars}-bar phrase"
    elif len(drops) >= 2:
        label = "Peak section"
        reason = f"{len(drops)} drops · {phrase_bars}-bar phrase"
    else:
        label = "Phrase loop"
        reason = f"{range_label} · {phrase_bars}-bar phrase"
    quality = "seamless" if loop_quality >= 0.78 else "smooth" if loop_quality >= 0.62 else "aligned"
    reason += f" · {quality} repeat ({key})"
    if vocal_penalty <= 0.15:
        reason += " · clean vocal seam"
    elif vocal_penalty >= 0.55:
        reason += " · vocal-aware seam"
    return label, reason


def _make_full_track_block(
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    *,
    reason: str,
) -> MusicBlock:
    track_duration = timeline.audio_duration_seconds
    n_beats = int(features.chroma_sync.shape[1]) if features.chroma_sync.ndim == 2 else 0
    loop_q = (
        _loop_quality(0, n_beats, features)
        if n_beats >= BEATS_PER_BAR
        else 0.5
    )
    drops = sum(1 for t in timeline.transients if t.type == "drop")
    return MusicBlock(
        id="block_full",
        start_s=0.0,
        end_s=track_duration,
        duration_s=track_duration,
        score=1.0,
        drop_count=drops,
        transient_count=len(timeline.transients),
        label="Full track",
        reason=reason,
        loop_quality=round(loop_q, 4),
        phrase_bars=0,
        key=features.meta.key,
    )


def _build_phrase_candidate(
    *,
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    start_idx: int,
    end_idx: int,
    phrase_bars: int,
    start_s: float,
    end_s: float,
    scope_lanes: dict[str, np.ndarray] | None,
    include_policy_scoring: bool,
) -> _Candidate:
    acoustic_loop_q = _loop_quality(start_idx, end_idx, features)
    vocal_pen = 0.0
    if scope_lanes is not None and scope_lanes.get("vocal") is not None:
        vocal_pen = vocal_boundary_penalty(
            scope_lanes,
            start_s,
            end_s,
            hop_length=features.meta.hop_length,
            sr=features.meta.sample_rate,
        )
    loop_q = acoustic_loop_q * (1.0 - VOCAL_SEAM_WEIGHT * vocal_pen)
    window_trans = _transients_in_window(timeline.transients, start_s, end_s)
    drops = [t for t in window_trans if t.type == "drop"]
    section = _section_for_window(sections, start_s, end_s)
    retention = 0.0
    if section:
        retention += section.energy * 0.35
        if section.is_repeated:
            retention += 0.25
    if drops:
        retention += min(len(drops) / 3.0, 1.0) * 0.25
    if any(abs(t.timestamp_ms / 1000.0 - start_s) <= 0.35 for t in drops):
        retention += 0.15
    if include_policy_scoring:
        policy_bonus = retention_bonus_for_window(
            scope_lanes,
            features.downbeat_times_s.tolist(),
            window_start_s=start_s,
            window_end_s=end_s,
        )
        retention += policy_bonus * 0.2
        pacing = pacing_density_score(
            scope_lanes,
            window_start_s=start_s,
            window_end_s=end_s,
        )
        if 0.25 <= pacing <= 0.85:
            retention += 0.08
    retention = min(1.0, retention)
    label, reason = _classify_candidate(
        start_s=start_s,
        end_s=end_s,
        phrase_bars=phrase_bars,
        drops=drops,
        section=section,
        loop_quality=loop_q,
        key=features.meta.key,
        vocal_penalty=vocal_pen,
    )
    return _Candidate(
        start_s=start_s,
        end_s=end_s,
        start_beat=start_idx,
        end_beat=end_idx,
        phrase_bars=phrase_bars,
        retention=retention,
        loop_quality=loop_q,
        section_label=section.label if section else None,
        is_repeated_section=bool(section and section.is_repeated),
        drop_count=len(drops),
        transient_count=len(window_trans),
        label=label,
        reason=reason,
        vocal_penalty=vocal_pen,
    )


def _enumerate_phrase_windows_for_starts(
    start_indices: list[int],
    *,
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    beat_times: np.ndarray,
    scope_lanes: dict[str, np.ndarray] | None,
    include_policy_scoring: bool,
    min_dur: float,
    max_dur: float | None = None,
    target_duration_s: float | None = None,
    on_progress: Callable[[str], None] | None = None,
) -> list[_Candidate]:
    candidates: list[_Candidate] = []
    total = len(start_indices)
    report_every = max(1, total // 12)
    for index, start_idx in enumerate(start_indices):
        if on_progress is not None and index % report_every == 0 and total > 0:
            on_progress(f"Scanning loop windows… {min(100, index * 100 // total)}%")
        if start_idx >= len(beat_times) - BEATS_PER_BAR:
            continue
        start_s = float(beat_times[start_idx])
        for phrase_bars in PHRASE_BAR_OPTIONS:
            phrase_beats = phrase_bars * BEATS_PER_BAR
            end_idx = start_idx + phrase_beats
            while end_idx < len(beat_times):
                end_s = float(beat_times[min(end_idx, len(beat_times) - 1)])
                duration = end_s - start_s
                if max_dur is not None and max_dur != float("inf") and duration >= max_dur - 1e-6:
                    break
                if duration >= min_dur - 1e-6 and (
                    target_duration_s is None
                    or _duration_in_target_window(duration, target_duration_s)
                ):
                    candidates.append(
                        _build_phrase_candidate(
                            timeline=timeline,
                            features=features,
                            sections=sections,
                            start_idx=start_idx,
                            end_idx=end_idx,
                            phrase_bars=phrase_bars,
                            start_s=start_s,
                            end_s=end_s,
                            scope_lanes=scope_lanes,
                            include_policy_scoring=include_policy_scoring,
                        )
                    )
                end_idx += phrase_beats
    return candidates


def _enumerate_all_phrase_candidates(
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    *,
    scope_lanes: dict[str, np.ndarray] | None = None,
    include_policy_scoring: bool = True,
    min_duration_s: float | None = None,
    max_duration_s: float | None = None,
    parallel_workers: int = 1,
    on_progress: Callable[[str], None] | None = None,
) -> list[_Candidate]:
    """Enumerate every scored phrase window (single pass for catalog / chip scores)."""
    track_duration = timeline.audio_duration_seconds
    min_dur = float(min_duration_s if min_duration_s is not None else CANONICAL_TARGET_DURATIONS_S[0])
    max_dur = max_duration_s
    if max_dur is None:
        max_dur = min(track_duration, CATALOG_MAX_WINDOW_S)
    else:
        max_dur = min(float(max_dur), track_duration)
    if track_duration <= min_dur:
        return []

    beat_times = features.beat_times_s
    downbeats = features.downbeat_times_s

    downbeat_indices = [_beat_index(beat_times, t) for t in downbeats]
    if not downbeat_indices:
        downbeat_indices = list(range(0, len(beat_times), BEATS_PER_BAR))

    workers = max(1, parallel_workers)
    if workers <= 1 or len(downbeat_indices) < workers * 2:
        return _enumerate_phrase_windows_for_starts(
            downbeat_indices,
            timeline=timeline,
            features=features,
            sections=sections,
            beat_times=beat_times,
            scope_lanes=scope_lanes,
            include_policy_scoring=include_policy_scoring,
            min_dur=min_dur,
            max_dur=max_dur,
            on_progress=on_progress,
        )

    chunks = np.array_split(np.asarray(downbeat_indices, dtype=int), workers)
    common = dict(
        timeline=timeline,
        features=features,
        sections=sections,
        beat_times=beat_times,
        scope_lanes=scope_lanes,
        include_policy_scoring=include_policy_scoring,
        min_dur=min_dur,
        max_dur=max_dur,
    )
    candidates: list[_Candidate] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                _enumerate_phrase_windows_for_starts,
                chunk.tolist(),
                **common,
            )
            for chunk in chunks
            if chunk.size > 0
        ]
        for future in futures:
            candidates.extend(future.result())
    return candidates


def _enumerate_phrase_candidates(
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    *,
    target_duration_s: float,
    scope_lanes: dict[str, np.ndarray] | None = None,
    include_policy_scoring: bool = True,
) -> list[_Candidate]:
    """Return phrase-aligned loop windows within drift tolerance of ``target_duration_s``."""
    track_duration = timeline.audio_duration_seconds
    if track_duration <= target_duration_s:
        return []

    beat_times = features.beat_times_s
    downbeats = features.downbeat_times_s
    min_dur, max_dur = target_duration_bounds(target_duration_s)

    downbeat_indices = [_beat_index(beat_times, t) for t in downbeats]
    if not downbeat_indices:
        downbeat_indices = list(range(0, len(beat_times), BEATS_PER_BAR))

    return _enumerate_phrase_windows_for_starts(
        downbeat_indices,
        timeline=timeline,
        features=features,
        sections=sections,
        beat_times=beat_times,
        scope_lanes=scope_lanes,
        include_policy_scoring=include_policy_scoring,
        min_dur=min_dur,
        max_dur=max_dur,
        target_duration_s=target_duration_s,
    )


def is_phrase_aligned_plan(plan: MusicBlockPlan) -> bool:
    """True when the plan offers at least one preset-length phrase loop (not full-track fallback)."""
    if plan.target_match_failed or plan.use_full_track:
        return False
    return any(block.id != "block_full" for block in plan.blocks)


def loop_qualities_from_plans(plans: dict[str, MusicBlockPlan]) -> list[TargetLoopQuality]:
    """Best loop quality per preset, excluding full-track fallback plans."""
    loop_qualities: list[TargetLoopQuality] = []
    for key, plan in plans.items():
        if not is_phrase_aligned_plan(plan):
            continue
        best = max(block.loop_quality for block in plan.blocks)
        loop_qualities.append(
            TargetLoopQuality(
                target_duration_s=float(key),
                loop_quality_pct=round(min(100.0, best * 100.0)),
            )
        )
    return loop_qualities


def _matchable_target_durations_from_candidates(
    all_candidates: list[_Candidate],
    *,
    track_duration_s: float,
) -> list[float]:
    return [
        float(duration)
        for duration in CANONICAL_TARGET_DURATIONS_S
        if duration <= track_duration_s
        and any(
            _duration_in_target_window(candidate.end_s - candidate.start_s, float(duration))
            for candidate in all_candidates
        )
    ]


def _select_block_plan_from_candidates(
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    *,
    target_duration_s: float,
    candidates: list[_Candidate],
    max_blocks: int = 5,
    selected_block_id: str | None = None,
    matchable_targets: list[float] | None = None,
) -> MusicBlockPlan:
    """Rank pre-enumerated phrase windows for one target length."""
    track_duration = timeline.audio_duration_seconds
    if track_duration <= target_duration_s:
        block = _make_full_track_block(
            timeline,
            features,
            reason="Track is already shorter than the target short length",
        )
        return MusicBlockPlan(
            target_duration_s=target_duration_s,
            track_duration_s=track_duration,
            selected_block_id=block.id,
            use_full_track=True,
            blocks=[block],
        )

    if not candidates:
        suggested_target: float | None = None
        if matchable_targets:
            suggested_target = min(
                matchable_targets,
                key=lambda candidate: abs(candidate - target_duration_s),
            )
        block = _make_full_track_block(
            timeline,
            features,
            reason="No phrase-aligned window for this target — preview the full track",
        )
        return MusicBlockPlan(
            target_duration_s=target_duration_s,
            track_duration_s=track_duration,
            selected_block_id=block.id,
            use_full_track=True,
            target_match_failed=True,
            suggested_target_duration_s=suggested_target,
            blocks=[block],
        )

    bpm = features.meta.global_bpm
    bar_period = (60.0 / bpm) * BEATS_PER_BAR

    def combined_score(c: _Candidate) -> float:
        drift = abs((c.end_s - c.start_s) - target_duration_s) / target_duration_s
        return c.loop_quality * 0.5 + c.retention * 0.35 - drift * 0.08

    ordered = sorted(candidates, key=combined_score, reverse=True)
    kept: list[_Candidate] = []
    min_gap = bar_period * 2
    for candidate in ordered:
        if all(
            abs(candidate.start_s - other.start_s) >= min_gap
            for other in kept
        ):
            kept.append(candidate)
        if len(kept) >= max_blocks:
            break
    kept.sort(key=lambda c: c.loop_quality, reverse=True)

    blocks = [
        MusicBlock(
            id=f"block_{chr(ord('a') + i)}",
            start_s=round(c.start_s, 3),
            end_s=round(c.end_s, 3),
            duration_s=round(c.end_s - c.start_s, 3),
            score=round(min(1.0, combined_score(c)), 4),
            drop_count=c.drop_count,
            transient_count=c.transient_count,
            label=c.label,
            reason=c.reason,
            loop_quality=round(c.loop_quality, 4),
            phrase_bars=c.phrase_bars,
            section_label=c.section_label,
            key=features.meta.key,
            is_repeated_section=c.is_repeated_section,
        )
        for i, c in enumerate(kept)
    ]

    auto_selected = selected_block_id or (blocks[0].id if blocks else None)
    if auto_selected and not any(b.id == auto_selected for b in blocks):
        auto_selected = blocks[0].id if blocks else None

    return MusicBlockPlan(
        target_duration_s=target_duration_s,
        track_duration_s=track_duration,
        selected_block_id=auto_selected,
        use_full_track=False,
        target_match_failed=False,
        suggested_target_duration_s=None,
        blocks=blocks,
    )


def list_target_loop_qualities(
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    *,
    scope_lanes: dict[str, np.ndarray] | None = None,
) -> list[TargetLoopQuality]:
    """Score each preset length by its best phrase-aligned seamless loop quality."""
    track_duration = timeline.audio_duration_seconds
    all_candidates = _enumerate_all_phrase_candidates(
        timeline,
        features,
        sections,
        scope_lanes=scope_lanes,
        include_policy_scoring=False,
        max_duration_s=CATALOG_MAX_WINDOW_S,
    )
    profiles: list[TargetLoopQuality] = []
    for duration in CANONICAL_TARGET_DURATIONS_S:
        if duration > track_duration:
            continue
        bucket = [
            candidate
            for candidate in all_candidates
            if _duration_in_target_window(candidate.end_s - candidate.start_s, float(duration))
        ]
        if not bucket:
            continue
        best = max(candidate.loop_quality for candidate in bucket)
        profiles.append(
            TargetLoopQuality(
                target_duration_s=float(duration),
                loop_quality_pct=round(min(100.0, best * 100.0)),
            )
        )
    return profiles


def list_matchable_target_durations(
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    *,
    scope_lanes: dict[str, np.ndarray] | None = None,
) -> list[float]:
    """Preset short lengths that have at least one phrase-aligned loop window."""
    return [
        profile.target_duration_s
        for profile in list_target_loop_qualities(
            timeline,
            features,
            sections,
            scope_lanes=scope_lanes,
        )
    ]


def find_nearest_matchable_target(
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    *,
    requested_target_s: float,
    scope_lanes: dict[str, np.ndarray] | None = None,
) -> float | None:
    """Pick the preset duration closest to ``requested_target_s`` that has phrase-aligned loops."""
    track_duration = timeline.audio_duration_seconds
    if track_duration <= requested_target_s:
        return None

    matchable = list_matchable_target_durations(
        timeline,
        features,
        sections,
        scope_lanes=scope_lanes,
    )
    if not matchable:
        return None

    return min(matchable, key=lambda candidate: abs(candidate - requested_target_s))


def suggest_music_blocks_advanced(
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    *,
    target_duration_s: float = 30.0,
    max_blocks: int = 5,
    selected_block_id: str | None = None,
    scope_lanes: dict[str, np.ndarray] | None = None,
) -> MusicBlockPlan:
    """Suggest blocks using downbeats, phrase lengths, sections, and beat-sync loop quality."""
    candidates = _enumerate_phrase_candidates(
        timeline,
        features,
        sections,
        target_duration_s=target_duration_s,
        scope_lanes=scope_lanes,
    )
    matchable_targets: list[float] | None = None
    if not candidates:
        matchable_targets = list_matchable_target_durations(
            timeline,
            features,
            sections,
            scope_lanes=scope_lanes,
        )
    return _select_block_plan_from_candidates(
        timeline,
        features,
        target_duration_s=target_duration_s,
        candidates=candidates,
        max_blocks=max_blocks,
        selected_block_id=selected_block_id,
        matchable_targets=matchable_targets,
    )


def _rescore_candidate_with_policy(
    candidate: _Candidate,
    *,
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    scope_lanes: dict[str, np.ndarray] | None,
) -> _Candidate:
    return _build_phrase_candidate(
        timeline=timeline,
        features=features,
        sections=sections,
        start_idx=candidate.start_beat,
        end_idx=candidate.end_beat,
        phrase_bars=candidate.phrase_bars,
        start_s=candidate.start_s,
        end_s=candidate.end_s,
        scope_lanes=scope_lanes,
        include_policy_scoring=True,
    )


def _prepare_catalog_bucket(
    candidates: list[_Candidate],
    *,
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    scope_lanes: dict[str, np.ndarray] | None,
) -> list[_Candidate]:
    """Fast-filter then policy-rescore only the likely winners for one target bucket."""
    if not candidates:
        return candidates
    if scope_lanes is None:
        return candidates
    prelim = sorted(
        candidates,
        key=lambda candidate: (candidate.loop_quality, candidate.retention),
        reverse=True,
    )[:CATALOG_POLICY_RESCORE_TOP_N]
    return [
        _rescore_candidate_with_policy(
            candidate,
            timeline=timeline,
            features=features,
            sections=sections,
            scope_lanes=scope_lanes,
        )
        for candidate in prelim
    ]


def _plan_catalog_entry(
    duration: int,
    *,
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    all_candidates: list[_Candidate],
    matchable_targets: list[float],
    scope_lanes: dict[str, np.ndarray] | None = None,
) -> tuple[str, MusicBlockPlan]:
    bucket = [
        candidate
        for candidate in all_candidates
        if _duration_in_target_window(candidate.end_s - candidate.start_s, float(duration))
    ]
    bucket = _prepare_catalog_bucket(
        bucket,
        timeline=timeline,
        features=features,
        sections=sections,
        scope_lanes=scope_lanes,
    )
    plan = _select_block_plan_from_candidates(
        timeline,
        features,
        target_duration_s=float(duration),
        candidates=bucket,
        matchable_targets=matchable_targets,
    )
    return str(int(duration)), plan


def build_block_catalog(
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    *,
    scope_lanes: dict[str, np.ndarray] | None = None,
    on_progress: Callable[[str], None] | None = None,
    max_workers: int | None = None,
) -> MusicBlockCatalog:
    """Precompute block plans for every preset target length on the track."""
    def progress(message: str) -> None:
        if on_progress is not None:
            on_progress(message)

    progress(
        f"Scanning phrase loops (≤{min(timeline.audio_duration_seconds, CATALOG_MAX_WINDOW_S):.0f}s windows, "
        f"{len(features.downbeat_times_s)} downbeats)"
    )
    workers = max_workers
    if workers is None:
        workers = max(1, (os.cpu_count() or 4))

    all_candidates = _enumerate_all_phrase_candidates(
        timeline,
        features,
        sections,
        scope_lanes=scope_lanes,
        include_policy_scoring=scope_lanes is None,
        max_duration_s=CATALOG_MAX_WINDOW_S,
        parallel_workers=workers,
        on_progress=progress,
    )
    matchable_targets = _matchable_target_durations_from_candidates(
        all_candidates,
        track_duration_s=timeline.audio_duration_seconds,
    )
    durations = [
        duration
        for duration in CANONICAL_TARGET_DURATIONS_S
        if duration <= timeline.audio_duration_seconds
    ]
    progress(
        f"Ranking {len(all_candidates)} loop windows for {len(durations)} preset lengths"
    )

    plans: dict[str, MusicBlockPlan] = {}
    for duration in durations:
        key, plan = _plan_catalog_entry(
            duration,
            timeline=timeline,
            features=features,
            sections=sections,
            all_candidates=all_candidates,
            matchable_targets=matchable_targets,
            scope_lanes=scope_lanes,
        )
        plans[key] = plan

    return MusicBlockCatalog(
        plans=plans,
        loop_qualities=loop_qualities_from_plans(plans),
    )
