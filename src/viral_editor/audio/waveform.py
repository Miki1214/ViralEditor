"""Waveform downsampling for the Audio Scope UI."""

from __future__ import annotations

import numpy as np

from viral_editor.audio.block_planner import DEFAULT_HOP_LENGTH, DEFAULT_SR
from viral_editor.audio.features import BeatSyncFeatures
from viral_editor.audio.loop_planner import (
    CANONICAL_TARGET_DURATIONS_S,
    list_target_loop_qualities,
)
from viral_editor.models import AudioTimeline, MusicBlockPlan, MusicStructurePlan, WaveformPayload, WaveformPoint


def downsample_envelope(
    onset_envelope: np.ndarray,
    *,
    duration_s: float,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
    max_points: int = 1000,
) -> list[WaveformPoint]:
    """Downsample an onset envelope to roughly ``max_points`` scope samples."""
    if onset_envelope.size == 0:
        return []

    peak = float(onset_envelope.max()) if onset_envelope.size else 1.0
    if peak <= 0:
        peak = 1.0
    normalized = onset_envelope / peak

    if normalized.size <= max_points:
        indices = np.arange(normalized.size)
    else:
        indices = np.linspace(0, normalized.size - 1, max_points).astype(int)

    points: list[WaveformPoint] = []
    for index in indices:
        time_s = index * hop_length / sr
        if time_s > duration_s:
            break
        points.append(
            WaveformPoint(
                t=round(time_s, 4),
                v=round(float(normalized[index]), 4),
            )
        )
    return points


def build_waveform_payload(
    timeline: AudioTimeline,
    onset_envelope: np.ndarray,
    block_plan: MusicBlockPlan,
    *,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
    structure: MusicStructurePlan | None = None,
    features: BeatSyncFeatures | None = None,
) -> WaveformPayload:
    blocks = sorted(block_plan.blocks, key=lambda block: block.loop_quality, reverse=True)
    downbeats: list[float] = []
    if features is not None:
        downbeats = [round(float(t), 4) for t in features.downbeat_times_s.tolist()]
    sections = structure.sections if structure is not None else []
    key = structure.key if structure is not None else (features.meta.key if features else None)
    beat_engine = structure.beat_engine if structure is not None else (
        features.meta.engine if features else None
    )

    if features is not None:
        sections = structure.sections if structure is not None else []
        loop_qualities = list_target_loop_qualities(timeline, features, sections)
        matchable_targets = [entry.target_duration_s for entry in loop_qualities]
        if loop_qualities:
            max_loop_pct = max(entry.loop_quality_pct for entry in loop_qualities)
            best_loop_targets = [
                entry.target_duration_s
                for entry in loop_qualities
                if entry.loop_quality_pct == max_loop_pct
            ]
        else:
            best_loop_targets = []
    else:
        loop_qualities = []
        matchable_targets = [
            float(duration)
            for duration in CANONICAL_TARGET_DURATIONS_S
            if duration <= timeline.audio_duration_seconds
        ]
        best_loop_targets = []

    return WaveformPayload(
        duration_s=timeline.audio_duration_seconds,
        global_bpm=timeline.global_bpm,
        key=key,
        beat_engine=beat_engine,
        points=downsample_envelope(
            onset_envelope,
            duration_s=timeline.audio_duration_seconds,
            hop_length=hop_length,
            sr=sr,
        ),
        transients=timeline.transients,
        downbeats=downbeats,
        sections=sections,
        blocks=blocks,
        selected_block_id=block_plan.selected_block_id,
        target_match_failed=block_plan.target_match_failed,
        suggested_target_duration_s=block_plan.suggested_target_duration_s,
        matchable_target_durations_s=matchable_targets,
        target_loop_qualities=loop_qualities,
        best_loop_target_durations_s=best_loop_targets,
    )
