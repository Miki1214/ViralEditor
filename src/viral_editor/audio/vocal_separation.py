"""Vocal stem separation and per-frame vocal activity for loop planning."""

from __future__ import annotations

import os
from pathlib import Path

import librosa
import numpy as np
import torch
from demucs.apply import apply_model
from demucs.audio import convert_audio
from demucs.pretrained import get_model

from viral_editor.utils.logging import get_logger

logger = get_logger(__name__)

DEMUCS_MODEL_NAME = "htdemucs"

# Demucs downloads htdemucs via torch hub; cache follows TORCH_HOME (default ~/.cache/torch).
# Override with DEMUCS_MODEL_CACHE to pin weights to a shared volume in Docker/CI.
DEMUCS_MODEL_CACHE = os.environ.get(
    "DEMUCS_MODEL_CACHE",
    os.environ.get("TORCH_HOME", os.path.expanduser("~/.cache/torch")),
)

VOCAL_ACTIVITY_FLOOR = 0.08


def _resample_signal(signal: np.ndarray, target_length: int) -> np.ndarray:
    if target_length <= 0:
        return np.zeros(0, dtype=np.float32)
    if signal.size == 0:
        return np.zeros(target_length, dtype=np.float32)
    if signal.size == target_length:
        return signal.astype(np.float32)
    src_x = np.linspace(0.0, 1.0, signal.size)
    dst_x = np.linspace(0.0, 1.0, target_length)
    return np.interp(dst_x, src_x, signal).astype(np.float32)


def _resample_envelope(envelope: np.ndarray, n_frames: int) -> np.ndarray:
    if n_frames <= 0:
        return np.zeros(0, dtype=np.float32)
    if envelope.size == 0:
        return np.zeros(n_frames, dtype=np.float32)
    if envelope.size == n_frames:
        return envelope.astype(np.float32)
    src_x = np.linspace(0.0, 1.0, envelope.size)
    dst_x = np.linspace(0.0, 1.0, n_frames)
    return np.interp(dst_x, src_x, envelope).astype(np.float32)


def _normalize_activity(envelope: np.ndarray) -> np.ndarray:
    if envelope.size == 0:
        return envelope.astype(np.float32)
    peak = float(np.percentile(envelope, 98))
    if peak <= 1e-9:
        peak = float(envelope.max())
    if peak <= 1e-9:
        return np.zeros_like(envelope, dtype=np.float32)
    return np.clip(envelope / peak, 0.0, 1.0).astype(np.float32)


def peak_normalize_lane(lane: np.ndarray) -> np.ndarray:
    """Peak-normalize a scope lane to 0–1 (shared with beat_detector fallback)."""
    return _normalize_activity(lane.astype(np.float32))


def separate_vocal_stem(
    audio_path: Path,
    *,
    model_sr: int = 44100,
) -> tuple[np.ndarray, int]:
    """Return mono vocal stem and the model sample rate."""
    resolved = audio_path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Audio file not found: {resolved}")

    if DEMUCS_MODEL_CACHE:
        os.environ.setdefault("TORCH_HOME", DEMUCS_MODEL_CACHE)

    model = get_model(DEMUCS_MODEL_NAME)
    model.eval()
    vocal_index = list(model.sources).index("vocals")

    # librosa decodes MP3/WAV without torchcodec (torchaudio 2.9+ requires it for load()).
    y, sr = librosa.load(str(resolved), sr=None, mono=False)
    if y.ndim == 1:
        wav_np = np.stack([y, y], axis=0)
    else:
        # librosa stereo layout is (channels, samples); Demucs expects the same.
        wav_np = y.astype(np.float32)
    wav = torch.from_numpy(wav_np).float()
    if wav.shape[0] == 1:
        wav = wav.repeat(2, 1)

    wav = convert_audio(wav, sr, model.samplerate, model.audio_channels)
    device = torch.device("cpu")
    wav = wav.to(device)
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / (ref.std() + 1e-8)

    with torch.no_grad():
        sources = apply_model(
            model,
            wav[None],
            device=device,
            progress=False,
            num_workers=0,
            shifts=1,
        )[0]

    vocals = sources[vocal_index].mean(dim=0).cpu().numpy().astype(np.float32)
    effective_sr = int(model.samplerate)
    if model_sr and model_sr != effective_sr:
        vocals = librosa.resample(vocals, orig_sr=effective_sr, target_sr=model_sr).astype(np.float32)
        effective_sr = model_sr

    logger.info(
        "Demucs vocal stem extracted — %.1fs @ %d Hz from %s (peak %.4f)",
        vocals.size / effective_sr,
        effective_sr,
        resolved.name,
        float(np.max(np.abs(vocals))) if vocals.size else 0.0,
    )
    return vocals, effective_sr


def compute_vocal_activity(
    audio_path: Path,
    *,
    hop_length: int,
    sr: int,
    n_frames: int,
    target_samples: int | None = None,
    frame_length: int | None = None,
) -> np.ndarray:
    """Peak-normalized RMS envelope of the vocal stem, aligned to scope-lane frame count."""
    vocal, model_sr = separate_vocal_stem(audio_path, model_sr=44100)
    if model_sr != sr:
        vocal = librosa.resample(vocal, orig_sr=model_sr, target_sr=sr).astype(np.float32)

    if target_samples is not None and target_samples > 0:
        vocal = _resample_signal(vocal, target_samples)

    rms_frame_length = frame_length if frame_length is not None else hop_length * 4
    rms_frame_length = min(rms_frame_length, max(len(vocal), hop_length))

    rms = librosa.feature.rms(
        y=vocal,
        hop_length=hop_length,
        frame_length=rms_frame_length,
    )[0]

    activity = _resample_envelope(rms, n_frames)
    activity = _normalize_activity(activity)

    logger.info(
        "Vocal activity lane — %d frames, peak %.3f, mean %.3f",
        n_frames,
        float(activity.max()) if activity.size else 0.0,
        float(activity.mean()) if activity.size else 0.0,
    )
    return activity
