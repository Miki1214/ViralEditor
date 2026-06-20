"""Structural segmentation from beat-synchronous self-similarity."""

from __future__ import annotations

import numpy as np
import librosa

from viral_editor.audio.features import BeatSyncFeatures
from viral_editor.models import MusicSection, Transient


def _snap_time_to_downbeat(time_s: float, downbeats: np.ndarray) -> float:
    if downbeats.size == 0:
        return time_s
    index = int(np.argmin(np.abs(downbeats - time_s)))
    return float(downbeats[index])


def _section_label(index: int, repetition_count: int, energy: float) -> str:
    if repetition_count >= 2 and energy >= 0.55:
        return f"Hook {index + 1}"
    if repetition_count >= 2:
        return f"Repeated {index + 1}"
    if energy >= 0.65:
        return f"Peak {index + 1}"
    return f"Section {index + 1}"


def analyze_structure(
    features: BeatSyncFeatures,
    *,
    transients: list[Transient],
    duration_s: float,
    beats_per_bar: int = 4,
) -> list[MusicSection]:
    """Segment track into labeled sections with repetition detection."""
    chroma = features.chroma_sync
    mfcc = features.mfcc_sync
    rms = features.rms_sync
    n_beats = chroma.shape[1] if chroma.ndim == 2 else 0
    if n_beats < 8:
        return [
            MusicSection(
                id="section_a",
                start_s=0.0,
                end_s=duration_s,
                start_beat=0,
                end_beat=max(n_beats - 1, 0),
                label="Full track",
                repetition_count=1,
                energy=0.5,
                is_repeated=False,
            )
        ]

    chroma_norm = librosa.util.normalize(chroma, axis=0)
    mfcc_norm = librosa.util.normalize(mfcc, axis=0)
    combined = np.vstack([chroma_norm, mfcc_norm * 0.6])

    try:
        boundaries = librosa.segment.agglomerative(combined, k=6)
    except Exception:
        boundaries = librosa.segment.agglomerative(chroma_norm, k=4)

    boundary_beats = sorted(set(int(b) for b in boundaries if 0 <= int(b) < n_beats))
    if not boundary_beats or boundary_beats[0] != 0:
        boundary_beats = [0, *boundary_beats]
    if boundary_beats[-1] != n_beats - 1:
        boundary_beats.append(n_beats - 1)

    beat_times = features.beat_times_s
    downbeats = features.downbeat_times_s
    beat_period = 60.0 / max(features.meta.global_bpm, 1e-6)
    prev_end_s = 0.0
    raw_sections: list[tuple[int, int, np.ndarray]] = []
    for start_beat, end_beat in zip(boundary_beats[:-1], boundary_beats[1:], strict=False):
        if end_beat <= start_beat:
            continue
        segment = combined[:, start_beat:end_beat]
        raw_sections.append((start_beat, end_beat, segment.mean(axis=1)))

    if not raw_sections:
        return []

    labels: list[int] = []
    label_vectors: list[np.ndarray] = []
    for _, _, vector in raw_sections:
        best_label = 0
        best_sim = -1.0
        for label_id, ref in enumerate(label_vectors):
            denom = np.linalg.norm(vector) * np.linalg.norm(ref)
            sim = float(np.dot(vector, ref) / denom) if denom > 1e-9 else 0.0
            if sim > best_sim:
                best_sim = sim
                best_label = label_id
        if best_sim >= 0.82:
            labels.append(best_label)
        else:
            labels.append(len(label_vectors))
            label_vectors.append(vector)

    label_counts: dict[int, int] = {}
    for label in labels:
        label_counts[label] = label_counts.get(label, 0) + 1

    sections: list[MusicSection] = []
    for index, ((start_beat, end_beat, _), label) in enumerate(
        zip(raw_sections, labels, strict=True)
    ):
        start_s = float(beat_times[min(start_beat, len(beat_times) - 1)])
        if end_beat >= len(beat_times):
            end_s = duration_s
        else:
            end_s = float(beat_times[end_beat])
        if downbeats.size:
            start_s = _snap_time_to_downbeat(start_s, downbeats)
        start_s = max(start_s, prev_end_s)
        if end_s <= start_s:
            end_s = min(duration_s, start_s + beats_per_bar * beat_period)
        end_s = min(end_s, duration_s)
        prev_end_s = end_s

        rms_seg = rms[:, start_beat:end_beat] if rms.size else np.array([[0.5]])
        energy = float(np.clip(rms_seg.mean(), 0.0, 1.0)) if rms_seg.size else 0.5
        drop_count = sum(
            1
            for t in transients
            if t.type == "drop" and start_s <= t.timestamp_ms / 1000.0 < end_s
        )
        rep_count = label_counts.get(label, 1)
        sections.append(
            MusicSection(
                id=f"section_{chr(ord('a') + index)}",
                start_s=round(start_s, 3),
                end_s=round(end_s, 3),
                start_beat=start_beat,
                end_beat=end_beat,
                label=_section_label(index, rep_count, energy),
                repetition_count=rep_count,
                energy=round(energy, 3),
                drop_count=drop_count,
                is_repeated=rep_count >= 2,
            )
        )
    return sections
