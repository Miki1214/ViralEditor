"""Beat-synchronous feature extraction and persistence."""

from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import librosa
import numpy as np

from viral_editor.audio.beat_tracker import BeatTrackResult
from viral_editor.models import DomainModel

KEY_PROFILES = {
    "C": np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]),
    "C#": np.roll(np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]), 1),
}
for _name, _profile in list(KEY_PROFILES.items()):
    if _name != "C":
        continue
for i, pitch in enumerate(["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]):
    KEY_PROFILES[pitch] = np.roll(
        np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]),
        i,
    )


class BeatFeaturesMeta(DomainModel):
    """Serializable metadata for beat-synchronous features."""

    engine: str
    global_bpm: float
    key: str
    n_beats: int
    n_downbeats: int
    hop_length: int
    sample_rate: int


@dataclass
class BeatSyncFeatures:
    """Beat-synchronous matrices for structure and loop planning."""

    meta: BeatFeaturesMeta
    beat_times_s: np.ndarray
    downbeat_times_s: np.ndarray
    chroma_sync: np.ndarray
    mfcc_sync: np.ndarray
    rms_sync: np.ndarray
    contrast_sync: np.ndarray
    tonnetz_sync: np.ndarray


def estimate_key(chroma: np.ndarray) -> str:
    """Krumhansl-Schmuckler key from mean chroma."""
    if chroma.size == 0:
        return "C"
    mean_chroma = chroma.mean(axis=1)
    if mean_chroma.sum() <= 0:
        return "C"
    mean_chroma = mean_chroma / mean_chroma.sum()
    best_key = "C"
    best_corr = -2.0
    for name, profile in KEY_PROFILES.items():
        profile_norm = profile / profile.sum()
        corr = float(np.corrcoef(mean_chroma, profile_norm)[0, 1])
        if corr > best_corr:
            best_corr = corr
            best_key = name
    return best_key


def _default_feature_workers() -> int:
    return min(4, os.cpu_count() or 4)


def _parallel_map(
    tasks: dict[str, Callable[[], np.ndarray]],
    *,
    max_workers: int,
) -> dict[str, np.ndarray]:
    if max_workers <= 1 or len(tasks) <= 1:
        return {name: fn() for name, fn in tasks.items()}

    results: dict[str, np.ndarray] = {}
    with ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as pool:
        futures = {pool.submit(fn): name for name, fn in tasks.items()}
        for future in futures:
            name = futures[future]
            results[name] = future.result()
    return results


def compute_beat_sync_features(
    y: np.ndarray,
    sr: int,
    beat_track: BeatTrackResult,
    *,
    hop_length: int = 512,
    n_fft: int = 2048,
    stft_power: np.ndarray | None = None,
    max_workers: int | None = None,
) -> BeatSyncFeatures:
    """Aggregate frame features to beat-synchronous matrices."""
    if stft_power is None:
        stft_power = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop_length)) ** 2

    workers = max(1, max_workers if max_workers is not None else _default_feature_workers())

    feature_tasks: dict[str, Callable[[], np.ndarray]] = {
        "chroma": lambda: librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length),
        "mfcc": lambda: librosa.feature.mfcc(
            S=stft_power,
            sr=sr,
            hop_length=hop_length,
            n_mfcc=13,
        ),
        "rms": lambda: librosa.feature.rms(S=stft_power),
        "contrast": lambda: librosa.feature.spectral_contrast(
            S=stft_power,
            sr=sr,
            hop_length=hop_length,
            n_fft=n_fft,
        ),
    }
    raw = _parallel_map(feature_tasks, max_workers=workers)
    tonnetz = librosa.feature.tonnetz(chroma=raw["chroma"])

    chroma = raw["chroma"]
    beat_frames = librosa.time_to_frames(beat_track.beat_times_s, sr=sr, hop_length=hop_length)
    beat_frames = np.clip(beat_frames, 0, chroma.shape[1] - 1)
    n_beats = int(beat_track.beat_times_s.size)

    def sync(feature: np.ndarray) -> np.ndarray:
        synced = librosa.util.sync(feature, beat_frames, aggregate=np.median)
        if synced.shape[1] > n_beats:
            synced = synced[:, :n_beats]
        elif synced.shape[1] < n_beats:
            pad = n_beats - synced.shape[1]
            synced = np.pad(synced, ((0, 0), (0, pad)), mode="edge")
        return synced

    key = estimate_key(chroma)
    meta = BeatFeaturesMeta(
        engine=beat_track.engine,
        global_bpm=round(beat_track.global_bpm, 2),
        key=key,
        n_beats=int(n_beats),
        n_downbeats=int(beat_track.downbeat_times_s.size),
        hop_length=hop_length,
        sample_rate=sr,
    )
    return BeatSyncFeatures(
        meta=meta,
        beat_times_s=beat_track.beat_times_s.astype(float),
        downbeat_times_s=beat_track.downbeat_times_s.astype(float),
        chroma_sync=sync(chroma),
        mfcc_sync=sync(raw["mfcc"]),
        rms_sync=sync(raw["rms"]),
        contrast_sync=sync(raw["contrast"]),
        tonnetz_sync=sync(tonnetz),
    )


def save_features(features: BeatSyncFeatures, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        beat_times_s=features.beat_times_s,
        downbeat_times_s=features.downbeat_times_s,
        chroma_sync=features.chroma_sync,
        mfcc_sync=features.mfcc_sync,
        rms_sync=features.rms_sync,
        contrast_sync=features.contrast_sync,
        tonnetz_sync=features.tonnetz_sync,
        meta_json=features.meta.model_dump_json(),
    )
    return path


def load_features(path: Path) -> BeatSyncFeatures:
    data = np.load(path, allow_pickle=False)
    meta = BeatFeaturesMeta.model_validate_json(str(data["meta_json"]))
    return BeatSyncFeatures(
        meta=meta,
        beat_times_s=data["beat_times_s"],
        downbeat_times_s=data["downbeat_times_s"],
        chroma_sync=data["chroma_sync"],
        mfcc_sync=data["mfcc_sync"],
        rms_sync=data["rms_sync"],
        contrast_sync=data["contrast_sync"],
        tonnetz_sync=data["tonnetz_sync"],
    )
