"""Audio DSP — beat and transient analysis."""

from viral_editor.audio.beat_detector import (
    AudioAnalysisError,
    AudioAnalysisResult,
    AudioDspConfig,
    analyze_audio,
    analyze_audio_with_envelope,
    fold_tempo,
    save_onset_envelope,
)

__all__ = [
    "AudioAnalysisError",
    "AudioAnalysisResult",
    "AudioDspConfig",
    "analyze_audio",
    "analyze_audio_with_envelope",
    "fold_tempo",
    "save_onset_envelope",
]
