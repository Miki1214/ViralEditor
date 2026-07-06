"""Text width measurement for caption layout and karaoke offsets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont


@dataclass(frozen=True)
class WordOffset:
    text: str
    x_px: float
    width_px: float


def measure_phrase_word_offsets(
    words: list[str],
    *,
    font_path: Path,
    font_size_px: int,
    word_spacing_px: float = 8.0,
) -> list[WordOffset]:
    """Measure horizontal pixel offsets for each word in a phrase."""
    font = ImageFont.truetype(str(font_path), font_size_px)
    offsets: list[WordOffset] = []
    cursor = 0.0
    for index, word in enumerate(words):
        width = float(font.getlength(word))
        offsets.append(WordOffset(text=word, x_px=cursor, width_px=width))
        cursor += width
        if index < len(words) - 1:
            cursor += word_spacing_px
    return offsets


def phrase_total_width_px(
    words: list[str],
    *,
    font_path: Path,
    font_size_px: int,
    word_spacing_px: float = 8.0,
) -> float:
    offsets = measure_phrase_word_offsets(
        words,
        font_path=font_path,
        font_size_px=font_size_px,
        word_spacing_px=word_spacing_px,
    )
    if not offsets:
        return 0.0
    last = offsets[-1]
    return last.x_px + last.width_px
