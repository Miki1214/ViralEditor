"""Waveform payload lanes and chroma from analysis artifacts."""

from __future__ import annotations

from pathlib import Path

from viral_editor.audio.beat_detector import AudioDspConfig, analyze_audio_with_envelope
from viral_editor.audio.waveform import build_scope_lane_series, build_waveform_payload
from viral_editor.models import MusicBlockPlan

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "audio"


def _fixture_payload(filename: str) -> tuple:
    path = FIXTURES_DIR / filename
    result = analyze_audio_with_envelope(
        path,
        config=AudioDspConfig(drop_percentile=0.85, min_drop_gap_ms=800)
        if filename == "validation_drop.wav"
        else None,
    )
    block_plan = MusicBlockPlan(
        target_duration_s=10.0,
        track_duration_s=result.timeline.audio_duration_seconds,
        blocks=[],
    )
    payload = build_waveform_payload(
        result.timeline,
        result.onset_envelope,
        block_plan,
        features=result.beat_features,
        scope_lanes=result.scope_lanes,
    )
    return result, payload


def test_waveform_payload_includes_beats_lanes_and_chroma() -> None:
    result, payload = _fixture_payload("validation_clicks.wav")

    assert payload.beats
    assert payload.downbeats
    assert len(payload.lanes) == 9
    lane_ids = {lane.id for lane in payload.lanes}
    assert "build" in lane_ids
    assert "drop_salience" in lane_ids
    assert "pacing_density" in lane_ids
    assert payload.chroma is not None
    assert len(payload.chroma.pitch_classes) == 12
    assert payload.chroma.tonic is not None

    for lane in payload.lanes:
        assert lane.points
        assert all(
            0.0 <= point.t <= result.timeline.audio_duration_seconds + 0.01
            for point in lane.points
        )
        assert all(0.0 <= point.v <= 1.0 for point in lane.points)


def test_validation_bass_low_band_dominates() -> None:
    _, payload = _fixture_payload("validation_bass.wav")
    lanes = {lane.id: lane for lane in payload.lanes}
    low = lanes["band_low"]
    mid = lanes["band_mid"]
    assert low.points
    assert mid.points
    assert max(point.v for point in low.points) >= max(point.v for point in mid.points)


def test_validation_drop_has_high_band_spike_near_hit() -> None:
    _, payload = _fixture_payload("validation_drop.wav")
    lanes = {lane.id: lane for lane in payload.lanes}
    high = lanes["band_high"]
    rms = lanes["rms"]

    near_hit = [point for point in high.points if 2.0 <= point.t <= 3.0]
    quiet = [point for point in high.points if point.t < 1.5]
    assert near_hit
    assert quiet
    assert max(point.v for point in near_hit) > max(point.v for point in quiet)

    near_rms = [point for point in rms.points if 2.0 <= point.t <= 3.0]
    assert near_rms
    assert max(point.v for point in near_rms) >= 0.5


def test_build_scope_lane_series_empty_when_missing() -> None:
    assert build_scope_lane_series(None, duration_s=5.0) == []
    assert build_scope_lane_series({}, duration_s=5.0) == []
