#!/usr/bin/env python3
"""Generate reference audio fixtures with documented ground-truth transients."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import soundfile as sf

from viral_editor.audio.beat_detector import AudioDspConfig, analyze_audio

REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "fixtures" / "audio"
SR = 22050


def write_wav(path: Path, y: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, y.astype(np.float32), SR)


def click_track(
    *,
    interval_s: float,
    duration_s: float,
    amplitude: float = 1.0,
    start_s: float = 0.5,
) -> np.ndarray:
    samples = int(SR * duration_s)
    y = np.zeros(samples, dtype=np.float32)
    t = start_s
    while t < duration_s:
        index = int(t * SR)
        y[index : min(index + 8, samples)] = amplitude
        t += interval_s
    return y


def add_impulse(y: np.ndarray, time_s: float, amplitude: float = 1.0) -> None:
    index = int(time_s * SR)
    end = min(index + 8, y.size)
    y[index:end] = amplitude


def add_bass_thump(
    y: np.ndarray,
    time_s: float,
    *,
    freq_hz: float = 55.0,
    duration_s: float = 0.12,
    amplitude: float = 0.95,
) -> None:
    start = int(time_s * SR)
    sample_count = int(duration_s * SR)
    if start >= y.size:
        return
    t = np.arange(sample_count, dtype=np.float32) / SR
    envelope = np.exp(-t * 22.0)
    tone = np.sin(2.0 * np.pi * freq_hz * t) * envelope * amplitude
    end = min(start + sample_count, y.size)
    y[start:end] += tone[: end - start]


def analyzed_transients(path: Path, *, config: AudioDspConfig | None = None) -> list[dict[str, object]]:
    timeline = analyze_audio(path, config=config)
    return [
        {
            "timestamp_ms": transient.timestamp_ms,
            "time_s": round(transient.timestamp_ms / 1000.0, 3),
            "type": transient.type,
            "amplitude_normalized": transient.amplitude_normalized,
        }
        for transient in timeline.transients
    ]


def build_clicks() -> tuple[np.ndarray, list[dict[str, object]]]:
    y = click_track(interval_s=0.5, duration_s=5.0)
    expected = [
        {
            "time_s": round(t, 3),
            "type": "onset",
            "tolerance_ms": 80,
            "note": "Any classified type — verifies onset timing",
        }
        for t in np.arange(0.5, 5.0, 0.5)
    ]
    return y, expected


def build_drop() -> tuple[np.ndarray, list[dict[str, object]]]:
    duration_s = 4.0
    y = np.zeros(int(SR * duration_s), dtype=np.float32)
    for t in (0.5, 1.0, 1.5):
        add_impulse(y, t, amplitude=0.08)
    drop_index = int(2.5 * SR)
    y[drop_index : drop_index + 12] = 1.0
    expected = [
        {"time_s": 2.5, "type": "drop", "tolerance_ms": 120, "note": "Loudest hit"},
        {"time_s": 0.5, "type": "onset", "tolerance_ms": 100},
        {"time_s": 1.0, "type": "onset", "tolerance_ms": 100},
        {"time_s": 1.5, "type": "onset", "tolerance_ms": 100},
    ]
    return y, expected


def build_bass() -> tuple[np.ndarray, list[dict[str, object]]]:
    duration_s = 4.0
    y = click_track(interval_s=0.25, duration_s=duration_s, amplitude=0.04, start_s=0.25)
    for t, freq in ((0.75, 45.0), (1.75, 55.0), (2.75, 50.0)):
        add_bass_thump(y, t, freq_hz=freq, duration_s=0.12, amplitude=0.55)
    expected = [
        {"time_s": 0.75, "type": "bass", "tolerance_ms": 150},
        {"time_s": 1.75, "type": "bass", "tolerance_ms": 150},
        {"time_s": 2.75, "type": "bass", "tolerance_ms": 150},
    ]
    return y, expected


def build_mixed() -> tuple[np.ndarray, list[dict[str, object]]]:
    duration_s = 5.0
    y = np.zeros(int(SR * duration_s), dtype=np.float32)
    add_bass_thump(y, 2.25, freq_hz=58.0, duration_s=0.12, amplitude=0.42)
    drop_index = int(3.75 * SR)
    y[drop_index : drop_index + 16] = 1.0
    expected = [
        {"time_s": 2.25, "type": "bass", "tolerance_ms": 150, "spatial_fx": "rotate"},
        {"time_s": 3.75, "type": "drop", "tolerance_ms": 120, "spatial_fx": "zoom"},
    ]
    return y, expected


def main() -> None:
    specs: list[tuple[str, str, callable]] = [
        (
            "validation_clicks.wav",
            "Metronome-like clicks every 0.5s — onset timing reference",
            build_clicks,
        ),
        (
            "validation_drop.wav",
            "Quiet ticks plus one loud hit at 2.5s — drop / zoom reference",
            build_drop,
        ),
        (
            "validation_bass.wav",
            "Low-frequency thumps — bass / rotate reference",
            build_bass,
        ),
        (
            "validation_mixed.wav",
            "Combined bass thumps and one drop — Spatial FX reference",
            build_mixed,
        ),
    ]

    manifest_samples: list[dict[str, object]] = []
    drop_config = AudioDspConfig(drop_percentile=0.85, min_drop_gap_ms=800)

    for filename, description, builder in specs:
        y, expected = builder()
        path = OUT_DIR / filename
        write_wav(path, y)

        analyze_config = drop_config if "drop" in filename else None
        verified = analyzed_transients(path, config=analyze_config)

        manifest_samples.append(
            {
                "file": filename,
                "description": description,
                "duration_s": round(len(y) / SR, 3),
                "sample_rate": SR,
                "expected_transients": expected,
                "verified_transients": verified,
            }
        )
        print(f"Wrote {path} ({len(y) / SR:.1f}s, {len(verified)} detected transients)")

    manifest = {
        "schema": "viral-editor/audio-fixture/1",
        "notes": (
            "expected_transients are ground-truth targets for manual or automated checks. "
            "type=onset means any transient type at that time. "
            "verified_transients are produced by the current analyze_audio classifier when this manifest was generated. "
            "Re-run: python scripts/generate_audio_fixtures.py"
        ),
        "samples": manifest_samples,
    }

    manifest_path = OUT_DIR / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path}")


if __name__ == "__main__":
    main()
