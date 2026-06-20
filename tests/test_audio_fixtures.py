"""Verify committed audio fixtures match manifest ground truth."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from viral_editor.audio.beat_detector import AudioDspConfig, analyze_audio

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "audio"
MANIFEST_PATH = FIXTURES_DIR / "manifest.json"


def _load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _matches_expected(
    verified: list[dict[str, object]],
    expected_time_s: float,
    expected_type: str,
    tolerance_ms: int,
) -> bool:
    for entry in verified:
        time_s = float(entry["time_s"])
        if abs(time_s - expected_time_s) * 1000.0 > tolerance_ms:
            continue
        if expected_type == "onset":
            return True
        if entry["type"] == expected_type:
            return True
    return False


@pytest.mark.parametrize(
    "sample",
    _load_manifest()["samples"],
    ids=lambda sample: sample["file"],
)
def test_fixture_matches_manifest(sample: dict) -> None:
    path = FIXTURES_DIR / sample["file"]
    assert path.is_file(), f"Missing fixture audio: {path}"

    config = (
        AudioDspConfig(drop_percentile=0.85, min_drop_gap_ms=800)
        if sample["file"] == "validation_drop.wav"
        else None
    )
    timeline = analyze_audio(path, config=config)
    verified = [
        {
            "time_s": round(transient.timestamp_ms / 1000.0, 3),
            "type": transient.type,
        }
        for transient in timeline.transients
    ]

    for expected in sample["expected_transients"]:
        expected_type = expected["type"]
        if expected_type == "onset":
            continue
        assert _matches_expected(
            verified,
            float(expected["time_s"]),
            expected_type,
            int(expected["tolerance_ms"]),
        ), (
            f"{sample['file']}: no {expected_type} near {expected['time_s']}s "
            f"(verified={verified})"
        )


def test_fixture_onset_grid_for_clicks() -> None:
    sample = next(item for item in _load_manifest()["samples"] if item["file"] == "validation_clicks.wav")
    path = FIXTURES_DIR / sample["file"]
    timeline = analyze_audio(path, config=AudioDspConfig(dedupe_window_ms=30))

    for expected in sample["expected_transients"]:
        time_ms = int(round(float(expected["time_s"]) * 1000.0))
        tolerance_ms = int(expected["tolerance_ms"])
        assert any(
            abs(transient.timestamp_ms - time_ms) <= tolerance_ms
            for transient in timeline.transients
        ), f"Missing onset near {expected['time_s']}s"
