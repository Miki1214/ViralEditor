"""Sophisticated loop and section-aware music block planner."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from viral_editor.audio.features import BeatSyncFeatures
from viral_editor.models import (
    AudioTimeline,
    MusicBlock,
    MusicBlockPlan,
    MusicSection,
    TargetLoopQuality,
    Transient,
)

BEATS_PER_BAR = 4
LOOP_MAX_DRIFT_RATIO = 0.28
PHRASE_BAR_OPTIONS = (4, 8, 16)
CANONICAL_TARGET_DURATIONS_S = (5, 10, 15, 20, 25, 30, 45, 60)


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


def _enumerate_phrase_candidates(
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    *,
    target_duration_s: float,
) -> list[_Candidate]:
    """Return phrase-aligned loop windows within drift tolerance of ``target_duration_s``."""
    track_duration = timeline.audio_duration_seconds
    if track_duration <= target_duration_s:
        return []

    beat_times = features.beat_times_s
    downbeats = features.downbeat_times_s
    bpm = features.meta.global_bpm
    min_dur = target_duration_s * (1.0 - LOOP_MAX_DRIFT_RATIO)
    max_dur = target_duration_s * (1.0 + LOOP_MAX_DRIFT_RATIO)

    downbeat_indices = [_beat_index(beat_times, t) for t in downbeats]
    if not downbeat_indices:
        downbeat_indices = list(range(0, len(beat_times), BEATS_PER_BAR))

    candidates: list[_Candidate] = []
    for start_idx in downbeat_indices:
        if start_idx >= len(beat_times) - BEATS_PER_BAR:
            continue
        start_s = float(beat_times[start_idx])
        for phrase_bars in PHRASE_BAR_OPTIONS:
            phrase_beats = phrase_bars * BEATS_PER_BAR
            end_idx = start_idx + phrase_beats
            while end_idx < len(beat_times):
                end_s = float(beat_times[min(end_idx, len(beat_times) - 1)])
                duration = end_s - start_s
                if duration > max_dur + 1e-6:
                    break
                if duration >= min_dur - 1e-6:
                    loop_q = _loop_quality(start_idx, end_idx, features)
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
                    retention = min(1.0, retention)
                    label, reason = _classify_candidate(
                        start_s=start_s,
                        end_s=end_s,
                        phrase_bars=phrase_bars,
                        drops=drops,
                        section=section,
                        loop_quality=loop_q,
                        key=features.meta.key,
                    )
                    candidates.append(
                        _Candidate(
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
                        )
                    )
                end_idx += phrase_beats
    return candidates


def list_target_loop_qualities(
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
) -> list[TargetLoopQuality]:
    """Score each preset length by its best phrase-aligned seamless loop quality."""
    track_duration = timeline.audio_duration_seconds
    profiles: list[TargetLoopQuality] = []
    for duration in CANONICAL_TARGET_DURATIONS_S:
        if duration > track_duration:
            continue
        candidates = _enumerate_phrase_candidates(
            timeline,
            features,
            sections,
            target_duration_s=float(duration),
        )
        if not candidates:
            continue
        best = max(c.loop_quality for c in candidates)
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
) -> list[float]:
    """Preset short lengths that have at least one phrase-aligned loop window."""
    return [
        profile.target_duration_s
        for profile in list_target_loop_qualities(timeline, features, sections)
    ]


def find_nearest_matchable_target(
    timeline: AudioTimeline,
    features: BeatSyncFeatures,
    sections: list[MusicSection],
    *,
    requested_target_s: float,
) -> float | None:
    """Pick the preset duration closest to ``requested_target_s`` that has phrase-aligned loops."""
    track_duration = timeline.audio_duration_seconds
    if track_duration <= requested_target_s:
        return None

    matchable = list_matchable_target_durations(timeline, features, sections)
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
) -> MusicBlockPlan:
    """Suggest blocks using downbeats, phrase lengths, sections, and beat-sync loop quality."""
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

    beat_times = features.beat_times_s
    bpm = features.meta.global_bpm
    bar_period = (60.0 / bpm) * BEATS_PER_BAR

    candidates = _enumerate_phrase_candidates(
        timeline,
        features,
        sections,
        target_duration_s=target_duration_s,
    )

    if not candidates:
        suggested_target = find_nearest_matchable_target(
            timeline,
            features,
            sections,
            requested_target_s=target_duration_s,
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
