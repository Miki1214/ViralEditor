"""Optional speech-to-text for caption auto-fill."""

from __future__ import annotations

from pathlib import Path

from viral_editor.models import CaptionWord


def transcribe_available() -> bool:
    try:
        import faster_whisper  # noqa: F401

        return True
    except ImportError:
        return False


def transcribe_audio(path: Path) -> tuple[str, list[CaptionWord]]:
    """Transcribe audio with word-level timestamps using faster-whisper."""
    if not path.is_file():
        raise FileNotFoundError(f"Audio not found: {path}")
    if not transcribe_available():
        raise RuntimeError(
            "faster-whisper is not installed. Install with: pip install faster-whisper"
        )

    from faster_whisper import WhisperModel

    model = WhisperModel("base", device="cpu", compute_type="int8")
    segments, _ = model.transcribe(str(path), word_timestamps=True)

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
