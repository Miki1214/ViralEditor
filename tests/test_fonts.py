"""Tests for font registry and text metrics."""

from __future__ import annotations

from pathlib import Path

import pytest

from viral_editor.utils.fonts import FONT_REGISTRY, resolve_font_path
from viral_editor.utils.text_metrics import measure_phrase_word_offsets


def test_font_registry_includes_montserrat_black() -> None:
    assert "Montserrat Black" in FONT_REGISTRY


def test_resolve_font_path_returns_existing_file() -> None:
    path = resolve_font_path("Montserrat Black")
    assert path is not None
    assert path.is_file()


def test_measure_phrase_word_offsets_returns_monotonic_x_positions() -> None:
    font_path = resolve_font_path("Montserrat Black")
    if font_path is None:
        pytest.skip("No font available for metrics test")
    offsets = measure_phrase_word_offsets(
        ["hello", "world"],
        font_path=font_path,
        font_size_px=48,
    )
    assert len(offsets) == 2
    assert offsets[0].x_px == pytest.approx(0.0)
    assert offsets[1].x_px > offsets[0].x_px
