"""Tests for caption line wrapping and word offset layout."""

from __future__ import annotations

import pytest

from viral_editor.utils.fonts import resolve_font_path
from viral_editor.utils.text_metrics import (
    fit_caption_layout,
    measure_word_offsets_in_line,
    wrap_words_to_lines,
)


@pytest.fixture
def font_path():
    path = resolve_font_path("Montserrat Black")
    if path is None:
        pytest.skip("No font available for layout tests")
    return path


def test_wrap_words_to_lines_splits_before_max_width(font_path) -> None:
    words = ["super", "long", "caption", "phrase", "overflow"]
    lines = wrap_words_to_lines(
        words,
        font_path=font_path,
        font_size_px=48,
        max_width_px=180,
        max_lines=2,
    )
    assert len(lines) == 2
    assert sum(len(line) for line in lines) == len(words)


def test_measure_word_offsets_match_joined_phrase(font_path) -> None:
    line_words = ["hello", "beautiful", "world"]
    offsets, line_width = measure_word_offsets_in_line(
        line_words,
        font_path=font_path,
        font_size_px=48,
    )
    assert len(offsets) == 3
    assert offsets[0].x_px == pytest.approx(0.0)
    assert offsets[-1].x_px + offsets[-1].width_px == pytest.approx(line_width, rel=0.01)


def test_fit_caption_layout_scales_down_for_narrow_width(font_path) -> None:
    words = ["this", "caption", "should", "fit", "inside", "safe", "zone"]
    lines, font_size = fit_caption_layout(
        words,
        font_path=font_path,
        base_font_size=64,
        max_width_px=220,
        max_lines=2,
    )
    assert len(lines) <= 2
    assert font_size < 64
