"""Beat/transient analysis via librosa (BeatViz core)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

from viral_editor.audio.beat_tracker import infer_beats
from viral_editor.audio.features import BeatSyncFeatures, compute_beat_sync_features, save_features
from viral_editor.models import AudioTimeline, DomainModel, Transient, TransientType
from viral_editor.utils.logging import get_logger

logger = get_logger(__name__)


class AudioAnalysisError(RuntimeError):
    """Raised when audio DSP fails."""


class AudioDspConfig(DomainModel):
    """Tunable parameters for onset and transient detection."""

    hop_length: int = 512
    target_sr: int = 22050
    n_fft: int = 2048
    drop_percentile: float = 0.92
    min_drop_gap_ms: int = 1500
    bass_band_hz: int = 200
    bass_energy_ratio: float = 0.6
    dedupe_window_ms: int = 60
    tempo_min_bpm: float = 60.0
    tempo_max_bpm: float = 180.0
    duration_tolerance_s: float = 0.5


@dataclass(frozen=True)
class AudioAnalysisResult:
    """Timeline plus reusable DSP features for downstream planners."""

    timeline: AudioTimeline
    onset_envelope: np.ndarray
    chroma: np.ndarray
    beat_features: BeatSyncFeatures
    scope_lanes: dict[str, np.ndarray]


_MID_BAND_MAX_HZ = 2000
_SCOPE_LANE_KEYS = ("rms", "band_low", "band_mid", "band_high")


def _compute_scope_lanes(
    y: np.ndarray,
    stft_mag: np.ndarray,
    freqs: np.ndarray,
    *,
    hop_length: int,
    sr: int,
    bass_band_hz: int,
) -> dict[str, np.ndarray]:
    """Per-frame envelopes aligned with the onset strength envelope."""
    n_frames = stft_mag.shape[1]
    low_mask = freqs <= bass_band_hz
    mid_mask = (freqs > bass_band_hz) & (freqs <= _MID_BAND_MAX_HZ)
    high_mask = freqs > _MID_BAND_MAX_HZ

    band_low = stft_mag[low_mask].sum(axis=0) if low_mask.any() else np.zeros(n_frames)
    band_mid = stft_mag[mid_mask].sum(axis=0) if mid_mask.any() else np.zeros(n_frames)
    band_high = stft_mag[high_mask].sum(axis=0) if high_mask.any() else np.zeros(n_frames)

    rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
    target_len = min(n_frames, rms.size, band_low.size)
    return {
        "rms": rms[:target_len].astype(np.float32),
        "band_low": band_low[:target_len].astype(np.float32),
        "band_mid": band_mid[:target_len].astype(np.float32),
        "band_high": band_high[:target_len].astype(np.float32),
    }


def _estimate_tempo(
    onset_env: np.ndarray,
    *,
    sr: int,
    hop_length: int,
) -> float:
    """Estimate global BPM from an onset envelope (librosa version tolerant)."""
    try:
        from librosa.feature.rhythm import tempo as tempo_fn
    except (ImportError, AttributeError):
        try:
            from librosa.feature import tempo as tempo_fn
        except ImportError:
            from librosa.beat import tempo as tempo_fn

    raw = tempo_fn(onset_envelope=onset_env, sr=sr, hop_length=hop_length)
    return float(np.atleast_1d(raw)[0])


def fold_tempo(
    bpm: float,
    *,
    min_bpm: float = 60.0,
    max_bpm: float = 180.0,
) -> float:
    """Fold half/double-tempo estimates into a musical BPM band."""
    folded = float(bpm)
    while folded < min_bpm:
        folded *= 2.0
    while folded > max_bpm:
        folded /= 2.0
    return folded


def _time_to_frame(time_s: float, *, sr: int, hop_length: int) -> int:
    return int(librosa.time_to_frames(time_s, sr=sr, hop_length=hop_length))


def _sample_envelope(
    onset_env: np.ndarray,
    time_s: float,
    *,
    sr: int,
    hop_length: int,
) -> float:
    frame = _time_to_frame(time_s, sr=sr, hop_length=hop_length)
    frame = min(max(frame, 0), len(onset_env) - 1)
    return float(onset_env[frame])


def _low_band_energy_ratio(
    stft_mag: np.ndarray,
    freqs: np.ndarray,
    frame: int,
    *,
    bass_band_hz: int,
) -> float:
    frame = min(max(frame, 0), stft_mag.shape[1] - 1)
    column = stft_mag[:, frame]
    total = float(column.sum()) + 1e-9
    low = float(column[freqs <= bass_band_hz].sum())
    return low / total


def _dedupe_onsets(
    onsets_s: np.ndarray,
    amplitudes: np.ndarray,
    *,
    dedupe_window_ms: int,
) -> tuple[np.ndarray, np.ndarray]:
    if len(onsets_s) == 0:
        return onsets_s, amplitudes

    order = np.argsort(onsets_s)
    onsets_s = onsets_s[order]
    amplitudes = amplitudes[order]

    kept_times: list[float] = []
    kept_amps: list[float] = []
    window_s = dedupe_window_ms / 1000.0

    for time_s, amp in zip(onsets_s, amplitudes, strict=True):
        if kept_times and (time_s - kept_times[-1]) * 1000.0 < dedupe_window_ms:
            if amp > kept_amps[-1]:
                kept_times[-1] = float(time_s)
                kept_amps[-1] = float(amp)
            continue
        kept_times.append(float(time_s))
        kept_amps.append(float(amp))

    return np.asarray(kept_times, dtype=float), np.asarray(kept_amps, dtype=float)


def _select_drops(
    onsets_s: np.ndarray,
    amplitudes_norm: np.ndarray,
    *,
    drop_percentile: float,
    min_drop_gap_ms: int,
) -> set[int]:
    if len(onsets_s) == 0:
        return set()

    threshold = float(np.quantile(amplitudes_norm, drop_percentile))
    candidates = [
        index
        for index, amp in enumerate(amplitudes_norm)
        if amp >= threshold
    ]
    candidates.sort(key=lambda index: amplitudes_norm[index], reverse=True)

    drops: list[int] = []
    min_gap_s = min_drop_gap_ms / 1000.0

    for index in candidates:
        time_s = onsets_s[index]
        if all(abs(time_s - onsets_s[other]) >= min_gap_s for other in drops):
            drops.append(index)

    return set(drops)


def _classify_transients(
    onsets_s: np.ndarray,
    amplitudes_norm: np.ndarray,
    stft_mag: np.ndarray,
    freqs: np.ndarray,
    *,
    config: AudioDspConfig,
) -> list[Transient]:
    drop_indices = _select_drops(
        onsets_s,
        amplitudes_norm,
        drop_percentile=config.drop_percentile,
        min_drop_gap_ms=config.min_drop_gap_ms,
    )

    transients: list[Transient] = []
    for index, (time_s, amplitude) in enumerate(zip(onsets_s, amplitudes_norm, strict=True)):
        if index in drop_indices:
            kind: TransientType = "drop"
        else:
            frame = _time_to_frame(time_s, sr=config.target_sr, hop_length=config.hop_length)
            low_ratio = _low_band_energy_ratio(
                stft_mag,
                freqs,
                frame,
                bass_band_hz=config.bass_band_hz,
            )
            kind = "bass" if low_ratio >= config.bass_energy_ratio else "percussive"

        transients.append(
            Transient(
                timestamp_ms=int(round(time_s * 1000.0)),
                amplitude_normalized=round(float(amplitude), 4),
                type=kind,
            )
        )

    transients.sort(key=lambda item: item.timestamp_ms)
    return transients


def analyze_audio(
    audio_path: Path,
    *,
    config: AudioDspConfig | None = None,
    expected_duration_s: float | None = None,
) -> AudioTimeline:
    """Analyze a music track and return beat/transient metadata."""
    return analyze_audio_with_envelope(
        audio_path,
        config=config,
        expected_duration_s=expected_duration_s,
    ).timeline


def analyze_audio_with_envelope(
    audio_path: Path,
    *,
    config: AudioDspConfig | None = None,
    expected_duration_s: float | None = None,
) -> AudioAnalysisResult:
    """Analyze audio and return the timeline plus the onset strength envelope."""
    cfg = config or AudioDspConfig()
    resolved = audio_path.resolve()

    if not resolved.is_file():
        raise AudioAnalysisError(f"Audio file not found: {resolved}")

    logger.info("Loading audio for DSP: %s", resolved)
    y, sr = librosa.load(resolved, sr=cfg.target_sr, mono=True)
    if y.size == 0:
        raise AudioAnalysisError(f"Audio file is empty: {resolved}")

    duration_s = float(librosa.get_duration(y=y, sr=sr))
    if expected_duration_s is not None:
        delta = abs(duration_s - expected_duration_s)
        if delta > cfg.duration_tolerance_s:
            logger.warning(
                "Audio decode duration (%.2fs) differs from ffprobe (%.2fs) by %.2fs",
                duration_s,
                expected_duration_s,
                delta,
            )

    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=cfg.hop_length)
    chroma = librosa.feature.chroma_stft(
        y=y,
        sr=sr,
        hop_length=cfg.hop_length,
        n_fft=cfg.n_fft,
    )

    raw_bpm = _estimate_tempo(onset_env, sr=sr, hop_length=cfg.hop_length)

    beat_track = infer_beats(resolved, y, sr, onset_env, hop_length=cfg.hop_length)
    global_bpm = beat_track.global_bpm
    if abs(global_bpm - raw_bpm) > 5.0:
        logger.info("Beat engine BPM %.1f (tempo estimate %.1f)", global_bpm, raw_bpm)

    beat_features = compute_beat_sync_features(
        y, sr, beat_track, hop_length=cfg.hop_length, n_fft=cfg.n_fft
    )

    onsets_s = librosa.onset.onset_detect(
        onset_envelope=onset_env,
        sr=sr,
        hop_length=cfg.hop_length,
        backtrack=True,
        units="time",
    )

    raw_amplitudes = np.asarray(
        [
            _sample_envelope(onset_env, float(time_s), sr=sr, hop_length=cfg.hop_length)
            for time_s in onsets_s
        ],
        dtype=float,
    )

    onsets_s, raw_amplitudes = _dedupe_onsets(
        np.asarray(onsets_s, dtype=float),
        raw_amplitudes,
        dedupe_window_ms=cfg.dedupe_window_ms,
    )

    max_amp = float(raw_amplitudes.max()) if raw_amplitudes.size else 1.0
    if max_amp <= 0:
        max_amp = 1.0
    amplitudes_norm = raw_amplitudes / max_amp

    stft_mag = np.abs(
        librosa.stft(y, n_fft=cfg.n_fft, hop_length=cfg.hop_length)
    )
    freqs = librosa.fft_frequencies(sr=sr, n_fft=cfg.n_fft)

    scope_lanes = _compute_scope_lanes(
        y,
        stft_mag,
        freqs,
        hop_length=cfg.hop_length,
        sr=sr,
        bass_band_hz=cfg.bass_band_hz,
    )

    transients = _classify_transients(
        onsets_s,
        amplitudes_norm,
        stft_mag,
        freqs,
        config=cfg,
    )

    timeline = AudioTimeline(
        global_bpm=round(global_bpm, 2),
        audio_duration_seconds=round(duration_s, 4),
        sample_rate=sr,
        transients=transients,
    )

    logger.info(
        "Audio analysis complete — %.1f BPM (%s), %d transients (%d drops), key=%s",
        timeline.global_bpm,
        beat_features.meta.engine,
        len(timeline.transients),
        sum(1 for t in timeline.transients if t.type == "drop"),
        beat_features.meta.key,
    )

    return AudioAnalysisResult(
        timeline=timeline,
        onset_envelope=onset_env,
        chroma=chroma,
        beat_features=beat_features,
        scope_lanes=scope_lanes,
    )


def save_onset_envelope(envelope: np.ndarray, path: Path) -> Path:
    """Persist the onset envelope for Phase 3 speed-ramp planning."""
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, envelope)
    return path


def save_beat_features(features: BeatSyncFeatures, path: Path) -> Path:
    return save_features(features, path)


def save_chroma(chroma: np.ndarray, path: Path) -> Path:
    """Persist chroma features for loop matching in the Audio Scope."""
    path.parent.mkdir(parents=True, exist_ok=True)
    np.save(path, chroma)
    return path


def save_scope_lanes(scope_lanes: dict[str, np.ndarray], path: Path) -> Path:
    """Persist per-frame scope lane envelopes for the Music detail UI."""
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **scope_lanes)
    return path


def load_scope_lanes(path: Path) -> dict[str, np.ndarray] | None:
    if not path.is_file():
        return None
    data = np.load(path)
    return {key: data[key] for key in data.files if key in _SCOPE_LANE_KEYS}
