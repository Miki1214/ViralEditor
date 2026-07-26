"""Tests for Whisper transcription helpers."""

from __future__ import annotations

import pytest

from viral_editor.audio.transcribe import (
    TranscribeOptions,
    VIRAL_WHISPER_COMPUTE_ENV,
    VIRAL_WHISPER_DEVICE_ENV,
    VIRAL_WHISPER_MODEL_ENV,
    clear_whisper_model_cache,
    normalize_transcribe_language,
    resolve_whisper_runtime_config,
    transcribe_audio,
)
from viral_editor.models import CaptionWord


def test_normalize_transcribe_language_auto_returns_none() -> None:
    assert normalize_transcribe_language("auto") is None
    assert normalize_transcribe_language("") is None
    assert normalize_transcribe_language(None) is None


def test_normalize_transcribe_language_accepts_supported_code() -> None:
    assert normalize_transcribe_language("pl") == "pl"
    assert normalize_transcribe_language(" EN ") == "en"


def test_normalize_transcribe_language_rejects_unknown_code() -> None:
    with pytest.raises(ValueError, match="Unsupported language"):
        normalize_transcribe_language("xx")


def test_transcribe_audio_passes_language_and_translate(monkeypatch, tmp_path) -> None:
    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(b"fake")
    clear_whisper_model_cache()

    captured: dict[str, object] = {}

    class FakeSegment:
        words = [
            type("W", (), {"word": " hello", "start": 0.1, "end": 0.4})(),
        ]
        text = "hello"
        start = 0.1
        end = 0.4

    class FakeModel:
        def transcribe(self, path, **kwargs):
            captured["path"] = path
            captured["kwargs"] = kwargs
            return [FakeSegment()], None

    monkeypatch.setattr("viral_editor.audio.transcribe.transcribe_available", lambda: True)
    monkeypatch.setattr(
        "viral_editor.audio.transcribe.get_whisper_model",
        lambda runtime=None: FakeModel(),
    )

    script, words = transcribe_audio(
        audio_path,
        options=TranscribeOptions(language="pl", translate=True),
    )

    assert script == "hello"
    assert len(words) == 1
    assert captured["kwargs"]["word_timestamps"] is True
    assert captured["kwargs"]["task"] == "translate"
    assert captured["kwargs"]["language"] == "pl"
    assert captured["kwargs"]["beam_size"] == 5
    assert captured["kwargs"]["vad_filter"] is True
    assert captured["kwargs"]["condition_on_previous_text"] is True


def test_transcribe_audio_honors_vad_and_condition_overrides(monkeypatch, tmp_path) -> None:
    audio_path = tmp_path / "clip.wav"
    audio_path.write_bytes(b"fake")
    clear_whisper_model_cache()

    captured: dict[str, object] = {}

    class FakeSegment:
        words = [
            type("W", (), {"word": " hello", "start": 0.1, "end": 0.4})(),
        ]
        text = "hello"
        start = 0.1
        end = 0.4

    class FakeModel:
        def transcribe(self, path, **kwargs):
            captured["kwargs"] = kwargs
            return [FakeSegment()], None

    monkeypatch.setattr("viral_editor.audio.transcribe.transcribe_available", lambda: True)
    monkeypatch.setattr(
        "viral_editor.audio.transcribe.get_whisper_model",
        lambda runtime=None: FakeModel(),
    )

    transcribe_audio(
        audio_path,
        vad_filter=False,
        condition_on_previous_text=False,
    )

    assert captured["kwargs"]["vad_filter"] is False
    assert captured["kwargs"]["condition_on_previous_text"] is False


def test_transcribe_from_audio_track_uses_vocal_stem_when_exported(
    monkeypatch, tmp_path
) -> None:
    from viral_editor.audio.transcribe_sources import transcribe_from_audio_track
    from viral_editor.config import JobConfig

    workspace = tmp_path / "job"
    (workspace / "input").mkdir(parents=True)
    audio_path = workspace / "input" / "track.mp3"
    audio_path.write_bytes(b"fake")
    vocal_wav = workspace / "temp" / "transcribe_scratch" / "vocal_stem_asr.wav"

    captured: dict[str, object] = {}

    def fake_export(audio_path, dest_wav, **kwargs):
        dest_wav.parent.mkdir(parents=True, exist_ok=True)
        dest_wav.write_bytes(b"wav")
        return dest_wav, 0.42

    def fake_transcribe(path, *, options=None, **kwargs):
        captured["path"] = path
        captured.update(kwargs)
        return "hello world", [CaptionWord(text="hello", start_s=0.1, end_s=0.4)]

    monkeypatch.setattr(
        "viral_editor.audio.vocal_separation.export_vocal_stem_wav_for_asr",
        fake_export,
    )
    monkeypatch.setattr(
        "viral_editor.audio.transcribe_sources.transcribe_audio",
        fake_transcribe,
    )

    config = JobConfig.model_validate(
        {
            "audio_path": str(audio_path),
            "output_path": str(workspace / "output.mp4"),
            "clips": [],
            "hook": {"text": "Hook"},
        }
    )
    result = transcribe_from_audio_track(
        config,
        None,
        workspace=workspace,
    )

    assert captured["path"] == vocal_wav
    assert captured["vad_filter"] is False
    assert captured["condition_on_previous_text"] is False
    assert result.script_text == "hello world"
    assert len(result.words) == 1


def test_resolve_whisper_runtime_config_prefers_gpu_profile(monkeypatch) -> None:
    monkeypatch.delenv(VIRAL_WHISPER_MODEL_ENV, raising=False)
    monkeypatch.delenv(VIRAL_WHISPER_DEVICE_ENV, raising=False)
    monkeypatch.delenv(VIRAL_WHISPER_COMPUTE_ENV, raising=False)
    monkeypatch.setattr("viral_editor.audio.transcribe._cuda_available", lambda: True)

    config = resolve_whisper_runtime_config()

    assert config.model_size == "large-v3"
    assert config.device == "cuda"
    assert config.compute_type == "float16"
    assert config.beam_size == 5
    assert config.vad_filter is True


def test_resolve_whisper_runtime_config_cpu_fallback(monkeypatch) -> None:
    monkeypatch.delenv(VIRAL_WHISPER_MODEL_ENV, raising=False)
    monkeypatch.delenv(VIRAL_WHISPER_DEVICE_ENV, raising=False)
    monkeypatch.delenv(VIRAL_WHISPER_COMPUTE_ENV, raising=False)
    monkeypatch.setattr("viral_editor.audio.transcribe._cuda_available", lambda: False)

    config = resolve_whisper_runtime_config()

    assert config.model_size == "small"
    assert config.device == "cpu"
    assert config.compute_type == "int8"


def test_get_whisper_model_uses_cache(monkeypatch) -> None:
    clear_whisper_model_cache()
    calls: list[tuple[str, str, str]] = []

    class FakeWhisperModel:
        def __init__(self, model_size, *, device, compute_type):
            calls.append((model_size, device, compute_type))

    monkeypatch.setattr("viral_editor.audio.transcribe.transcribe_available", lambda: True)

    import faster_whisper

    monkeypatch.setattr(faster_whisper, "WhisperModel", FakeWhisperModel)
    from viral_editor.audio.transcribe import WhisperRuntimeConfig, get_whisper_model

    runtime = WhisperRuntimeConfig(
        model_size="small",
        device="cpu",
        compute_type="int8",
        beam_size=5,
        vad_filter=True,
    )
    get_whisper_model(runtime)
    get_whisper_model(runtime)
    assert calls == [("small", "cpu", "int8")]

