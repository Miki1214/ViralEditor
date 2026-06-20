"""Tests for structural segmentation."""

from __future__ import annotations

import numpy as np

from viral_editor.audio.features import BeatFeaturesMeta, BeatSyncFeatures
from viral_editor.audio.structure import analyze_structure
from viral_editor.models import Transient


def _synthetic_abab_features(*, n_beats: int = 64, bpm: float = 120.0) -> BeatSyncFeatures:
    """Two alternating timbre/harmony segments (ABAB)."""
    beat_times = np.arange(n_beats) * (60.0 / bpm)
    downbeats = beat_times[::4]
    chroma_a = np.array([1.0, 0.1, 0.1, 0.1, 0.8, 0.1, 0.1, 0.1, 0.6, 0.1, 0.1, 0.1])
    chroma_b = np.array([0.1, 0.1, 0.9, 0.1, 0.1, 0.7, 0.1, 0.1, 0.1, 0.8, 0.1, 0.1])
    mfcc_a = np.ones(13) * 0.2
    mfcc_b = np.ones(13) * 0.9

    chroma = np.zeros((12, n_beats))
    mfcc = np.zeros((13, n_beats))
    rms = np.zeros((1, n_beats))
    half = n_beats // 2
    for beat in range(n_beats):
        segment = 0 if (beat // 8) % 2 == 0 else 1
        chroma[:, beat] = chroma_a if segment == 0 else chroma_b
        mfcc[:, beat] = mfcc_a if segment == 0 else mfcc_b
        rms[0, beat] = 0.4 if segment == 0 else 0.75

    meta = BeatFeaturesMeta(
        engine="test",
        global_bpm=bpm,
        key="C",
        n_beats=n_beats,
        n_downbeats=len(downbeats),
        hop_length=512,
        sample_rate=22050,
    )
    return BeatSyncFeatures(
        meta=meta,
        beat_times_s=beat_times.astype(float),
        downbeat_times_s=downbeats.astype(float),
        chroma_sync=chroma,
        mfcc_sync=mfcc,
        rms_sync=rms,
        contrast_sync=np.zeros((7, n_beats)),
        tonnetz_sync=np.zeros((6, n_beats)),
    )


def test_abab_track_detects_multiple_sections() -> None:
    features = _synthetic_abab_features(n_beats=64)
    sections = analyze_structure(
        features,
        transients=[],
        duration_s=float(features.beat_times_s[-1] + 60.0 / features.meta.global_bpm),
    )
    assert len(sections) >= 2
    labels = {section.label for section in sections}
    assert len(labels) >= 2


def test_repeated_sections_flagged() -> None:
    features = _synthetic_abab_features(n_beats=80)
    sections = analyze_structure(
        features,
        transients=[
            Transient(timestamp_ms=5000, amplitude_normalized=0.9, type="drop"),
        ],
        duration_s=float(features.beat_times_s[-1] + 60.0 / features.meta.global_bpm),
    )
    assert any(section.is_repeated for section in sections)


def test_sections_do_not_overlap() -> None:
    features = _synthetic_abab_features(n_beats=64)
    duration_s = float(features.beat_times_s[-1] + 60.0 / features.meta.global_bpm)
    sections = analyze_structure(features, transients=[], duration_s=duration_s)
    assert len(sections) >= 2
    for left, right in zip(sections, sections[1:], strict=False):
        assert left.end_s <= right.start_s + 0.001
        assert left.start_s < left.end_s


def test_short_track_returns_single_section() -> None:
    features = _synthetic_abab_features(n_beats=4)
    sections = analyze_structure(features, transients=[], duration_s=8.0)
    assert len(sections) == 1
    assert sections[0].label == "Full track"


def test_section_labels_include_duration_energy_and_drops() -> None:
    features = _synthetic_abab_features(n_beats=80)
    sections = analyze_structure(
        features,
        transients=[
            Transient(timestamp_ms=5000, amplitude_normalized=0.9, type="drop"),
            Transient(timestamp_ms=9000, amplitude_normalized=0.85, type="drop"),
        ],
        duration_s=float(features.beat_times_s[-1] + 60.0 / features.meta.global_bpm),
    )
    assert sections
    for section in sections:
        assert " · " in section.label
        assert any(token.endswith("s") or ":" in token for token in section.label.split(" · "))
        assert any(token in section.label for token in ("loud", "mid", "quiet"))
