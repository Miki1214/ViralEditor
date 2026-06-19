"""Waveform downsampling for the Audio Scope UI."""

from __future__ import annotations

import numpy as np

from viral_editor.audio.block_planner import DEFAULT_HOP_LENGTH, DEFAULT_SR
from viral_editor.models import AudioTimeline, MusicBlockPlan, WaveformPayload, WaveformPoint


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
) -> WaveformPayload:
    return WaveformPayload(
        duration_s=timeline.audio_duration_seconds,
        global_bpm=timeline.global_bpm,
        points=downsample_envelope(
            onset_envelope,
            duration_s=timeline.audio_duration_seconds,
            hop_length=hop_length,
            sr=sr,
        ),
        transients=timeline.transients,
        blocks=block_plan.blocks,
        selected_block_id=block_plan.selected_block_id,
    )
