"""Vocal stem separation and per-frame vocal activity for loop planning."""

from __future__ import annotations

import os
from collections.abc import Callable
from functools import lru_cache
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

# Parallel CPU chunk jobs for apply_model (Demucs ``-j`` / ``num_workers``).
# Override with DEMUCS_NUM_WORKERS or AudioDspConfig.demucs_workers.
DEMUCS_NUM_WORKERS_ENV = "DEMUCS_NUM_WORKERS"
DEMUCS_SHIFTS_ENV = "DEMUCS_SHIFTS"
DEMUCS_OVERLAP_ENV = "DEMUCS_OVERLAP"
DEMUCS_DEVICE_ENV = "DEMUCS_DEVICE"
# Cap parallel chunk jobs — extra workers raise CPU % but rarely cut wall time on CPU
# (memory bandwidth bound). Override via env/config for experimentation.
DEMUCS_MAX_DEFAULT_WORKERS = 8

_CPU_ONLY_TORCH_WARNED = False

# Minimum Demucs vocal-stem energy share to treat a track as having vocals.
VOCAL_STEM_SHARE_MIN = 0.15
# Mix-relative scaling: vocal RMS / (mix p90 * ratio) before optional polish.
VOCAL_MIX_RATIO_REF = 0.55


def _logical_cpu_count() -> int:
    return os.cpu_count() or 4


def _physical_cpu_count() -> int:
    """Best-effort physical core count (SMT siblings excluded when OS exposes it)."""
    fn = getattr(os, "process_cpu_count", None)
    if fn is not None:
        count = fn()
        if count and count > 0:
            return int(count)
    logical = _logical_cpu_count()
    # Laptops / small CPUs: treat logical count as physical.
    if logical <= 8:
        return logical
    # Typical desktop SMT: logical ≈ 2× physical (e.g. 16P / 32T).
    return max(logical // 2, 1)


def _default_demucs_workers() -> int:
    logical = _logical_cpu_count()
    if logical <= 2:
        return 1
    physical = _physical_cpu_count()
    return max(1, min(physical, logical, DEMUCS_MAX_DEFAULT_WORKERS))


def resolve_demucs_shifts(requested: int | None = None) -> int:
    if requested is not None:
        return max(0, int(requested))
    env = os.environ.get(DEMUCS_SHIFTS_ENV)
    if env is not None and env.strip() != "":
        return max(0, int(env))
    return 0


def resolve_demucs_overlap(requested: float | None = None) -> float:
    if requested is not None:
        return float(max(0.0, min(0.5, requested)))
    env = os.environ.get(DEMUCS_OVERLAP_ENV)
    if env is not None and env.strip() != "":
        return float(max(0.0, min(0.5, float(env))))
    return 0.15


def resolve_demucs_workers(requested: int | None = None) -> int:
    """Return Demucs ``num_workers`` for parallel segment inference on CPU."""
    if requested is not None:
        return max(0, int(requested))
    env = os.environ.get(DEMUCS_NUM_WORKERS_ENV)
    if env is not None and env.strip() != "":
        return max(0, int(env))
    return _default_demucs_workers()


def _torch_is_cpu_only_build() -> bool:
    return getattr(torch.version, "cuda", None) is None


def _warn_cpu_only_torch_once() -> None:
    global _CPU_ONLY_TORCH_WARNED
    if _CPU_ONLY_TORCH_WARNED or not _torch_is_cpu_only_build():
        return
    _CPU_ONLY_TORCH_WARNED = True
    logger.warning(
        "PyTorch CPU-only build (%s) — Demucs runs on CPU. "
        "For NVIDIA GPU: pip install --upgrade torch torchaudio "
        "--index-url https://download.pytorch.org/whl/cu124",
        torch.__version__,
    )


def resolve_demucs_device(requested: str | None = None) -> torch.device:
    """Pick inference device: ``auto`` prefers CUDA, ``cuda`` requires GPU, ``cpu`` forces CPU."""
    preference = (requested or os.environ.get(DEMUCS_DEVICE_ENV) or "auto").strip().lower()
    if preference not in {"auto", "cuda", "cpu"}:
        raise ValueError(f"Unsupported Demucs device preference: {preference!r}")

    if preference == "cpu":
        return torch.device("cpu")

    if torch.cuda.is_available():
        return torch.device("cuda")

    if preference == "cuda":
        if _torch_is_cpu_only_build():
            raise RuntimeError(
                "Demucs GPU requested but PyTorch is a CPU-only build "
                f"({torch.__version__}). Reinstall with CUDA wheels, e.g. "
                "pip install --upgrade torch torchaudio "
                "--index-url https://download.pytorch.org/whl/cu124"
            )
        raise RuntimeError(
            "Demucs GPU requested but torch.cuda.is_available() is False "
            "(driver/CUDA runtime missing or no compatible GPU)."
        )

    _warn_cpu_only_torch_once()
    return torch.device("cpu")


def demucs_device_label(device: torch.device) -> str:
    if device.type == "cuda":
        try:
            index = device.index if device.index is not None else torch.cuda.current_device()
            name = torch.cuda.get_device_name(index)
            return f"GPU · {name}"
        except Exception:
            return "GPU · CUDA"
    return "CPU"


def demucs_progress_label(device: torch.device, *, num_workers: int) -> str:
    label = demucs_device_label(device)
    if device.type == "cpu" and num_workers > 0:
        chunk_word = "chunks" if num_workers != 1 else "chunk"
        return f"{label} · {num_workers} parallel {chunk_word}"
    return label


def _configure_torch_threads_for_demucs(num_workers: int) -> None:
    """Avoid oversubscribing CPU when Demucs runs multiple segment jobs."""
    logical = _logical_cpu_count()
    if num_workers > 0:
        threads = max(1, logical // num_workers)
        torch.set_num_threads(threads)
    else:
        torch.set_num_threads(logical)


@lru_cache(maxsize=1)
def _load_demucs_model(model_name: str = DEMUCS_MODEL_NAME):
    if DEMUCS_MODEL_CACHE:
        os.environ.setdefault("TORCH_HOME", DEMUCS_MODEL_CACHE)
    model = get_model(model_name)
    model.eval()
    return model


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


def _calibrate_vocal_activity(vocal_rms: np.ndarray, mix_rms: np.ndarray | None) -> np.ndarray:
    """Scale vocal RMS against mix loudness instead of peak-normalizing leakage to 1.0."""
    if vocal_rms.size == 0:
        return vocal_rms.astype(np.float32)
    if mix_rms is None or mix_rms.size == 0:
        return _normalize_activity(vocal_rms)

    n = min(vocal_rms.size, mix_rms.size)
    vocal = vocal_rms[:n].astype(np.float32)
    mix = mix_rms[:n].astype(np.float32)
    mix_ref = float(np.percentile(mix, 90))
    if mix_ref <= 1e-9:
        mix_ref = float(mix.max()) or 1e-9

    scaled = np.clip(vocal / (mix_ref * VOCAL_MIX_RATIO_REF), 0.0, 1.0).astype(np.float32)
    polish_peak = float(np.percentile(scaled, 98))
    if polish_peak > 0.25:
        scaled = np.clip(scaled / polish_peak, 0.0, 1.0).astype(np.float32)
    return scaled


def peak_normalize_lane(lane: np.ndarray) -> np.ndarray:
    """Peak-normalize a scope lane to 0–1."""
    return _normalize_activity(lane.astype(np.float32))


def _vocal_stem_cache_valid(
    cache_path: Path,
    audio_path: Path,
    *,
    shifts: int,
    overlap: float,
) -> bool:
    try:
        stat = audio_path.stat()
        with np.load(cache_path, allow_pickle=False) as data:
            if int(data["mtime_ns"][0]) != stat.st_mtime_ns:
                return False
            if int(data["size"][0]) != stat.st_size:
                return False
            if int(data["shifts"][0]) != shifts:
                return False
            if not np.isclose(float(data["overlap"][0]), overlap, rtol=0.0, atol=1e-6):
                return False
            if str(data["model"][0]) != DEMUCS_MODEL_NAME:
                return False
    except (FileNotFoundError, OSError, KeyError, ValueError, IndexError):
        return False
    return True


def _load_vocal_stem_cache(
    cache_path: Path,
    audio_path: Path,
    *,
    shifts: int,
    overlap: float,
) -> tuple[np.ndarray, int, dict[str, float]] | None:
    if not _vocal_stem_cache_valid(cache_path, audio_path, shifts=shifts, overlap=overlap):
        return None
    with np.load(cache_path, allow_pickle=False) as data:
        vocals = data["vocals"].astype(np.float32)
        sr = int(data["sr"][0])
        shares = {
            name: float(data[f"share_{name}"][0])
            for name in ("drums", "bass", "other", "vocals")
        }
    logger.info("Loaded cached Demucs vocal stem from %s", cache_path.name)
    return vocals, sr, shares


def _save_vocal_stem_cache(
    cache_path: Path,
    audio_path: Path,
    vocals: np.ndarray,
    sr: int,
    shares: dict[str, float],
    *,
    shifts: int,
    overlap: float,
) -> None:
    stat = audio_path.stat()
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        cache_path,
        vocals=vocals.astype(np.float32),
        sr=np.array([sr], dtype=np.int32),
        mtime_ns=np.array([stat.st_mtime_ns], dtype=np.int64),
        size=np.array([stat.st_size], dtype=np.int64),
        shifts=np.array([shifts], dtype=np.int32),
        overlap=np.array([overlap], dtype=np.float32),
        model=np.array([DEMUCS_MODEL_NAME]),
        share_drums=np.array([shares.get("drums", 0.0)], dtype=np.float32),
        share_bass=np.array([shares.get("bass", 0.0)], dtype=np.float32),
        share_other=np.array([shares.get("other", 0.0)], dtype=np.float32),
        share_vocals=np.array([shares.get("vocals", 0.0)], dtype=np.float32),
    )


def separate_vocal_stem(
    audio_path: Path,
    *,
    model_sr: int = 44100,
    num_workers: int | None = None,
    demucs_shifts: int | None = None,
    demucs_overlap: float | None = None,
    demucs_device: str | None = None,
    cache_path: Path | None = None,
    on_cache_hit: Callable[[], None] | None = None,
) -> tuple[np.ndarray, int, dict[str, float]]:
    """Return mono vocal stem, model sample rate, and per-stem energy shares."""
    resolved = audio_path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(f"Audio file not found: {resolved}")

    shifts = resolve_demucs_shifts(demucs_shifts)
    overlap = resolve_demucs_overlap(demucs_overlap)
    if cache_path is not None:
        cached = _load_vocal_stem_cache(
            cache_path,
            resolved,
            shifts=shifts,
            overlap=overlap,
        )
        if cached is not None:
            if on_cache_hit is not None:
                on_cache_hit()
            return cached

    model = _load_demucs_model(DEMUCS_MODEL_NAME)
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
    device = resolve_demucs_device(demucs_device)
    wav = wav.to(device)
    ref = wav.mean(0)
    wav = (wav - ref.mean()) / (ref.std() + 1e-8)

    workers = resolve_demucs_workers(num_workers)
    if device.type == "cpu":
        _configure_torch_threads_for_demucs(workers)
    else:
        workers = 0

    with torch.inference_mode():
        sources = apply_model(
            model,
            wav[None],
            device=device,
            progress=False,
            num_workers=workers,
            shifts=shifts,
            overlap=overlap,
        )[0]

    energies: dict[str, float] = {}
    for index, name in enumerate(model.sources):
        mono = sources[index].mean(dim=0).cpu().numpy().astype(np.float32)
        energies[name] = float(np.sqrt(np.mean(mono**2)))
    total_energy = sum(energies.values()) or 1.0
    shares = {name: energy / total_energy for name, energy in energies.items()}

    vocals = sources[vocal_index].mean(dim=0).cpu().numpy().astype(np.float32)
    effective_sr = int(model.samplerate)
    if model_sr and model_sr != effective_sr:
        vocals = librosa.resample(vocals, orig_sr=effective_sr, target_sr=model_sr).astype(np.float32)
        effective_sr = model_sr

    logger.info(
        "Demucs vocal stem extracted — %.1fs @ %d Hz from %s (peak %.4f, share %.3f, %s, workers=%d, shifts=%d, overlap=%.2f)",
        vocals.size / effective_sr,
        effective_sr,
        resolved.name,
        float(np.max(np.abs(vocals))) if vocals.size else 0.0,
        shares.get("vocals", 0.0),
        demucs_device_label(device),
        workers,
        shifts,
        overlap,
    )
    if cache_path is not None:
        _save_vocal_stem_cache(
            cache_path,
            resolved,
            vocals,
            effective_sr,
            shares,
            shifts=shifts,
            overlap=overlap,
        )
    return vocals, effective_sr, shares


def compute_vocal_activity(
    audio_path: Path,
    *,
    hop_length: int,
    sr: int,
    n_frames: int,
    target_samples: int | None = None,
    frame_length: int | None = None,
    mix_rms: np.ndarray | None = None,
    num_workers: int | None = None,
    demucs_shifts: int | None = None,
    demucs_overlap: float | None = None,
    demucs_device: str | None = None,
    cache_path: Path | None = None,
    on_cache_hit: Callable[[], None] | None = None,
) -> np.ndarray:
    """Mix-relative RMS envelope of the vocal stem, aligned to scope-lane frame count."""
    vocal, model_sr, shares = separate_vocal_stem(
        audio_path,
        model_sr=44100,
        num_workers=num_workers,
        demucs_shifts=demucs_shifts,
        demucs_overlap=demucs_overlap,
        demucs_device=demucs_device,
        cache_path=cache_path,
        on_cache_hit=on_cache_hit,
    )
    vocal_share = float(shares.get("vocals", 0.0))
    if vocal_share < VOCAL_STEM_SHARE_MIN:
        logger.info(
            "Vocal stem share %.3f below %.2f — treating track as instrumental",
            vocal_share,
            VOCAL_STEM_SHARE_MIN,
        )
        return np.zeros(n_frames, dtype=np.float32)

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
    activity = _calibrate_vocal_activity(activity, mix_rms)

    logger.info(
        "Vocal activity lane — %d frames, share %.3f, peak %.3f, mean %.3f",
        n_frames,
        vocal_share,
        float(activity.max()) if activity.size else 0.0,
        float(activity.mean()) if activity.size else 0.0,
    )
    return activity
