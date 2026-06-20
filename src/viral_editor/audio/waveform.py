"""Waveform downsampling for the Audio Scope UI."""

from __future__ import annotations

import numpy as np

from viral_editor.audio.block_planner import DEFAULT_HOP_LENGTH, DEFAULT_SR
from viral_editor.audio.features import BeatSyncFeatures
from viral_editor.audio.loop_planner import (
    CANONICAL_TARGET_DURATIONS_S,
    list_target_loop_qualities,
)
from viral_editor.models import (
    AudioTimeline,
    ChromaGram,
    MusicBlockPlan,
    MusicStructurePlan,
    ScopeLaneSeries,
    TargetLoopQuality,
    WaveformPayload,
    WaveformPoint,
)

PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
SCOPE_LANE_LABELS = {
    "rms": "Loudness",
    "band_low": "Low",
    "band_mid": "Mid",
    "band_high": "High",
    "build": "Build",
    "drop_salience": "Drop salience",
    "flux_low": "Low flux",
    "flux_high": "High flux",
    "pacing_density": "Pacing",
    "vocal": "Vocal",
}
SCOPE_LANE_ORDER = (
    "rms",
    "band_low",
    "band_mid",
    "band_high",
    "build",
    "drop_salience",
    "flux_low",
    "flux_high",
    "pacing_density",
    "vocal",
)


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


def build_chroma_gram(
    features: BeatSyncFeatures,
    *,
    max_cols: int = 400,
) -> ChromaGram | None:
    chroma = features.chroma_sync
    if chroma.size == 0 or chroma.ndim != 2:
        return None
    n_beats = chroma.shape[1]
    stride = max(1, int(np.ceil(n_beats / max_cols)))
    indices = list(range(0, n_beats, stride))
    beat_times = features.beat_times_s
    times = [round(float(beat_times[index]), 4) for index in indices if index < beat_times.size]
    frames: list[list[float]] = []
    for index in indices:
        column = chroma[:, index].astype(float)
        peak = float(column.max()) if column.size else 1.0
        if peak <= 0:
            peak = 1.0
        frames.append([round(float(value / peak), 4) for value in column])
    if not frames:
        return None
    return ChromaGram(
        times=times,
        pitch_classes=list(PITCH_CLASSES),
        frames=frames,
        tonic=features.meta.key,
    )


def build_scope_lane_series(
    scope_lanes: dict[str, np.ndarray] | None,
    *,
    duration_s: float,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
) -> list[ScopeLaneSeries]:
    if not scope_lanes:
        return []
    lanes: list[ScopeLaneSeries] = []
    for lane_id in SCOPE_LANE_ORDER:
        envelope = scope_lanes.get(lane_id)
        if envelope is None or envelope.size == 0:
            continue
        lanes.append(
            ScopeLaneSeries(
                id=lane_id,
                label=SCOPE_LANE_LABELS.get(lane_id, lane_id),
                points=downsample_envelope(
                    envelope,
                    duration_s=duration_s,
                    hop_length=hop_length,
                    sr=sr,
                ),
            )
        )
    return lanes


def build_waveform_payload(
    timeline: AudioTimeline,
    onset_envelope: np.ndarray,
    block_plan: MusicBlockPlan,
    *,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
    structure: MusicStructurePlan | None = None,
    features: BeatSyncFeatures | None = None,
    scope_lanes: dict[str, np.ndarray] | None = None,
    loop_qualities: list[TargetLoopQuality] | None = None,
) -> WaveformPayload:
    blocks = sorted(block_plan.blocks, key=lambda block: block.loop_quality, reverse=True)
    downbeats: list[float] = []
    beats: list[float] = []
    if features is not None:
        downbeats = [round(float(t), 4) for t in features.downbeat_times_s.tolist()]
        beats = [round(float(t), 4) for t in features.beat_times_s.tolist()]
    sections = structure.sections if structure is not None else []
    key = structure.key if structure is not None else (features.meta.key if features else None)
    beat_engine = structure.beat_engine if structure is not None else (
        features.meta.engine if features else None
    )

    if features is not None:
        sections = structure.sections if structure is not None else []
        if loop_qualities is None:
            loop_qualities = list_target_loop_qualities(
                timeline,
                features,
                sections,
                scope_lanes=scope_lanes,
            )
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
        beats=beats,
        downbeats=downbeats,
        sections=sections,
        lanes=build_scope_lane_series(
            scope_lanes,
            duration_s=timeline.audio_duration_seconds,
            hop_length=hop_length,
            sr=sr,
        ),
        chroma=build_chroma_gram(features) if features is not None else None,
        blocks=blocks,
        selected_block_id=block_plan.selected_block_id,
        target_match_failed=block_plan.target_match_failed,
        suggested_target_duration_s=block_plan.suggested_target_duration_s,
        matchable_target_durations_s=matchable_targets,
        target_loop_qualities=loop_qualities,
        best_loop_target_durations_s=best_loop_targets,
    )
