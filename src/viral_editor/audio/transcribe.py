"""Optional speech-to-text for caption auto-fill."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from viral_editor.models import CaptionWord
from viral_editor.utils.ffmpeg import run_ffmpeg
from viral_editor.utils.logging import get_logger

logger = get_logger(__name__)

VIRAL_WHISPER_MODEL_ENV = "VIRAL_WHISPER_MODEL"
VIRAL_WHISPER_DEVICE_ENV = "VIRAL_WHISPER_DEVICE"
VIRAL_WHISPER_COMPUTE_ENV = "VIRAL_WHISPER_COMPUTE_TYPE"
VIRAL_WHISPER_BEAM_SIZE_ENV = "VIRAL_WHISPER_BEAM_SIZE"
VIRAL_WHISPER_VAD_FILTER_ENV = "VIRAL_WHISPER_VAD_FILTER"

WHISPER_MODEL_CHOICES = (
    "tiny",
    "base",
    "small",
    "medium",
    "large-v2",
    "large-v3",
)
WHISPER_COMPUTE_CPU = frozenset({"int8", "float32"})
WHISPER_COMPUTE_CUDA = frozenset({"float16", "int8_float16", "float32", "int8"})

_MODEL_CACHE: dict[tuple[str, str, str], Any] = {}
_MODEL_CACHE_LOCK = threading.Lock()


@dataclass(frozen=True)
class TranscribeOptions:
    """Whisper inference options for caption auto-transcribe."""

    language: str | None = None
    translate: bool = False


@dataclass(frozen=True)
class WhisperRuntimeConfig:
    """Resolved faster-whisper runtime profile."""

    model_size: str
    device: str
    compute_type: str
    beam_size: int
    vad_filter: bool

    def cache_key(self) -> tuple[str, str, str]:
        return (self.model_size, self.device, self.compute_type)

    def summary(self) -> str:
        return f"{self.model_size}@{self.device}/{self.compute_type}"


WHISPER_LANGUAGE_CHOICES: tuple[tuple[str, str], ...] = (
    ("auto", "Auto-detect"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("pl", "Polish"),
    ("ru", "Russian"),
    ("uk", "Ukrainian"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("zh", "Chinese"),
    ("ar", "Arabic"),
    ("hi", "Hindi"),
    ("nl", "Dutch"),
    ("tr", "Turkish"),
    ("sv", "Swedish"),
    ("cs", "Czech"),
    ("ro", "Romanian"),
    ("hu", "Hungarian"),
)

_WHISPER_LANGUAGE_CODES = {code for code, _label in WHISPER_LANGUAGE_CHOICES if code != "auto"}


def normalize_transcribe_language(language: str | None) -> str | None:
    """Return a Whisper ISO language code, or None for auto-detect."""
    if language is None:
        return None
    normalized = language.strip().lower()
    if not normalized or normalized == "auto":
        return None
    if normalized not in _WHISPER_LANGUAGE_CODES:
        supported = ", ".join(sorted(_WHISPER_LANGUAGE_CODES))
        raise ValueError(f"Unsupported language '{language}'. Supported codes: {supported}")
    return normalized


def transcribe_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def _cuda_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean (got {raw!r})")


def resolve_whisper_device(preference: str | None = None) -> str:
    """Pick inference device: auto prefers CUDA when available."""
    choice = (preference or os.environ.get(VIRAL_WHISPER_DEVICE_ENV) or "auto").strip().lower()
    if choice not in {"auto", "cuda", "cpu"}:
        raise ValueError(f"Unsupported Whisper device preference: {choice!r}")
    if choice == "cpu":
        return "cpu"
    if _cuda_available():
        return "cuda"
    if choice == "cuda":
        raise RuntimeError(
            "Whisper GPU requested but CUDA is not available. "
            "Install CUDA-enabled PyTorch or set VIRAL_WHISPER_DEVICE=cpu."
        )
    return "cpu"


def _default_model_for_device(device: str) -> str:
    return "medium" if device == "cuda" else "small"


def _default_compute_for_device(device: str) -> str:
    return "float16" if device == "cuda" else "int8"


def _normalize_compute_type(compute_type: str, *, device: str) -> str:
    normalized = compute_type.strip().lower()
    allowed = WHISPER_COMPUTE_CUDA if device == "cuda" else WHISPER_COMPUTE_CPU
    if normalized not in allowed:
        supported = ", ".join(sorted(allowed))
        raise ValueError(
            f"Unsupported Whisper compute type {compute_type!r} for device {device!r}. "
            f"Supported: {supported}"
        )
    return normalized


def resolve_whisper_runtime_config() -> WhisperRuntimeConfig:
    """Resolve faster-whisper runtime settings from env with GPU-first defaults."""
    device = resolve_whisper_device()
    model_size = (
        os.environ.get(VIRAL_WHISPER_MODEL_ENV) or _default_model_for_device(device)
    ).strip().lower()
    if model_size not in WHISPER_MODEL_CHOICES:
        supported = ", ".join(WHISPER_MODEL_CHOICES)
        raise ValueError(f"Unsupported Whisper model {model_size!r}. Supported: {supported}")

    compute_raw = os.environ.get(VIRAL_WHISPER_COMPUTE_ENV) or _default_compute_for_device(device)
    compute_type = _normalize_compute_type(compute_raw, device=device)

    beam_env = os.environ.get(VIRAL_WHISPER_BEAM_SIZE_ENV)
    beam_size = int(beam_env) if beam_env not in (None, "") else 5
    if beam_size < 1:
        raise ValueError("VIRAL_WHISPER_BEAM_SIZE must be >= 1")

    vad_filter = _parse_bool_env(VIRAL_WHISPER_VAD_FILTER_ENV, default=True)
    return WhisperRuntimeConfig(
        model_size=model_size,
        device=device,
        compute_type=compute_type,
        beam_size=beam_size,
        vad_filter=vad_filter,
    )


def clear_whisper_model_cache() -> None:
    """Drop cached Whisper models (for tests or config changes)."""
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE.clear()


def get_whisper_model(runtime: WhisperRuntimeConfig | None = None):
    """Return a cached faster-whisper model for the resolved runtime profile."""
    if not transcribe_available():
        raise RuntimeError(
            "faster-whisper is not installed. Install with: pip install faster-whisper"
        )

    config = runtime or resolve_whisper_runtime_config()
    key = config.cache_key()
    with _MODEL_CACHE_LOCK:
        cached = _MODEL_CACHE.get(key)
        if cached is not None:
            return cached

    from faster_whisper import WhisperModel

    logger.info(
        "Loading Whisper model profile %s (beam=%d, vad=%s)",
        config.summary(),
        config.beam_size,
        config.vad_filter,
    )
    model = WhisperModel(
        config.model_size,
        device=config.device,
        compute_type=config.compute_type,
    )
    with _MODEL_CACHE_LOCK:
        _MODEL_CACHE[key] = model
    return model


def extract_audio_track(
    source: Path,
    dest: Path,
    *,
    start_s: float | None = None,
    end_s: float | None = None,
) -> Path:
    """Extract a mono 16 kHz wav segment from a media file for ASR."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    args: list[str] = []
    if start_s is not None:
        args += ["-ss", f"{start_s:.3f}"]
    args += ["-i", str(source)]
    if end_s is not None:
        args += ["-to", f"{end_s:.3f}"]
    args += ["-vn", "-ac", "1", "-ar", "16000", "-y", str(dest)]
    run_ffmpeg(args)
    return dest


def transcribe_audio(
    path: Path,
    *,
    options: TranscribeOptions | None = None,
    runtime: WhisperRuntimeConfig | None = None,
) -> tuple[str, list[CaptionWord]]:
    """Transcribe audio with word-level timestamps using faster-whisper."""
    if not path.is_file():
        raise FileNotFoundError(f"Audio not found: {path}")

    opts = options or TranscribeOptions()
    config = runtime or resolve_whisper_runtime_config()
    model = get_whisper_model(config)

    transcribe_kwargs: dict[str, object] = {
        "word_timestamps": True,
        "task": "translate" if opts.translate else "transcribe",
        "beam_size": config.beam_size,
        "vad_filter": config.vad_filter,
        "condition_on_previous_text": True,
    }
    if opts.language:
        transcribe_kwargs["language"] = opts.language
    segments, _ = model.transcribe(str(path), **transcribe_kwargs)

    words: list[CaptionWord] = []
    script_parts: list[str] = []
    for segment in segments:
        if segment.words:
            for word in segment.words:
                text = (word.word or "").strip()
                if not text:
                    continue
                script_parts.append(text)
                words.append(
                    CaptionWord(
                        text=text,
                        start_s=round(float(word.start), 4),
                        end_s=round(float(word.end), 4),
                    )
                )
        elif segment.text.strip():
            script_parts.append(segment.text.strip())
            words.append(
                CaptionWord(
                    text=segment.text.strip(),
                    start_s=round(float(segment.start), 4),
                    end_s=round(float(segment.end), 4),
                )
            )

    return " ".join(script_parts), words
