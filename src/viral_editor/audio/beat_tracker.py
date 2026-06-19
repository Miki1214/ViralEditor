"""Beat and downbeat inference — beat-this neural tracker with librosa fallback."""

from __future__ import annotations

import os
from dataclasses import dataclass

import librosa
import numpy as np
from pathlib import Path

from viral_editor.utils.logging import get_logger

logger = get_logger(__name__)

BEATS_PER_BAR = 4
MODEL_CACHE_DIR = Path(os.environ.get("BEAT_THIS_MODEL_DIR", "/models"))


@dataclass(frozen=True)
class BeatTrackResult:
    """Beat grid from analysis."""

    engine: str
    beat_times_s: np.ndarray
    downbeat_times_s: np.ndarray
    global_bpm: float


def _bpm_from_beats(beat_times_s: np.ndarray) -> float:
    if beat_times_s.size < 2:
        return 120.0
    intervals = np.diff(beat_times_s)
    intervals = intervals[(intervals > 0.05) & (intervals < 2.0)]
    if intervals.size == 0:
        return 120.0
    return float(60.0 / np.median(intervals))


def _fold_bpm(bpm: float, *, min_bpm: float = 60.0, max_bpm: float = 180.0) -> float:
    folded = float(bpm)
    while folded < min_bpm:
        folded *= 2.0
    while folded > max_bpm:
        folded /= 2.0
    return folded


def _estimate_downbeats_librosa(
    beat_times_s: np.ndarray,
    onset_envelope: np.ndarray,
    *,
    sr: int,
    hop_length: int,
    beats_per_bar: int = BEATS_PER_BAR,
) -> np.ndarray:
    """Pick downbeat phase via beat-synchronous onset energy (4/4 assumed)."""
    if beat_times_s.size == 0:
        return np.array([], dtype=float)

    beat_frames = librosa.time_to_frames(beat_times_s, sr=sr, hop_length=hop_length)
    beat_frames = np.clip(beat_frames, 0, len(onset_envelope) - 1)
    beat_strength = onset_envelope[beat_frames]

    n_beats = len(beat_times_s)
    if n_beats < beats_per_bar:
        return beat_times_s[:1].copy()

    best_phase = 0
    best_score = -1.0
    for phase in range(beats_per_bar):
        indices = np.arange(phase, n_beats, beats_per_bar)
        score = float(beat_strength[indices].sum()) if indices.size else 0.0
        if score > best_score:
            best_score = score
            best_phase = phase

    downbeat_indices = np.arange(best_phase, n_beats, beats_per_bar)
    return beat_times_s[downbeat_indices].astype(float)


def _infer_beats_beat_this(audio_path: Path) -> BeatTrackResult | None:
    try:
        from beat_this.inference import File2Beats
    except ImportError:
        return None

    try:
        MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("TORCH_HOME", str(MODEL_CACHE_DIR))
        tracker = File2Beats(checkpoint_path="final0", device="cpu", dbn=False)
        beats, downbeats = tracker(str(audio_path.resolve()))
        beat_times = np.asarray(beats, dtype=float)
        downbeat_times = np.asarray(downbeats, dtype=float)
        if beat_times.size == 0:
            return None
        bpm = _fold_bpm(_bpm_from_beats(beat_times))
        logger.info(
            "beat-this: %d beats, %d downbeats, %.1f BPM",
            beat_times.size,
            downbeat_times.size,
            bpm,
        )
        return BeatTrackResult(
            engine="beat-this",
            beat_times_s=beat_times,
            downbeat_times_s=downbeat_times,
            global_bpm=bpm,
        )
    except Exception as exc:
        logger.warning("beat-this unavailable, using librosa fallback: %s", exc)
        return None


def _infer_beats_librosa(
    y: np.ndarray,
    sr: int,
    onset_envelope: np.ndarray,
    *,
    hop_length: int,
) -> BeatTrackResult:
    tempo, beat_frames = librosa.beat.beat_track(
        y=y,
        sr=sr,
        hop_length=hop_length,
        onset_envelope=onset_envelope,
        units="time",
    )
    beat_times = np.asarray(beat_frames, dtype=float).reshape(-1)
    if beat_times.size == 0:
        duration = len(y) / sr
        bpm = _fold_bpm(float(np.atleast_1d(tempo)[0]))
        beat_period = 60.0 / bpm
        beat_times = np.arange(0.0, duration, beat_period)

    downbeat_times = _estimate_downbeats_librosa(
        beat_times,
        onset_envelope,
        sr=sr,
        hop_length=hop_length,
    )
    bpm = _fold_bpm(_bpm_from_beats(beat_times))
    logger.info(
        "librosa beats: %d beats, %d downbeats, %.1f BPM",
        beat_times.size,
        downbeat_times.size,
        bpm,
    )
    return BeatTrackResult(
        engine="librosa",
        beat_times_s=beat_times,
        downbeat_times_s=downbeat_times,
        global_bpm=bpm,
    )


def infer_beats(
    audio_path: Path,
    y: np.ndarray,
    sr: int,
    onset_envelope: np.ndarray,
    *,
    hop_length: int,
) -> BeatTrackResult:
    """Run beat-this when available, else librosa beat_track + downbeat heuristic."""
    neural = _infer_beats_beat_this(audio_path)
    if neural is not None:
        return neural
    return _infer_beats_librosa(y, sr, onset_envelope, hop_length=hop_length)
