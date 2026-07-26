"""Text width measurement and caption line layout."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import ImageFont


@dataclass(frozen=True)
class WordOffset:
    text: str
    x_px: float
    width_px: float


@dataclass(frozen=True)
class CaptionLineLayout:
    words: list[str]
    line_width_px: float
    word_offsets: list[WordOffset]


def _load_font(font_path: Path, font_size_px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(font_path), font_size_px)


def line_width_px(
    line_words: list[str],
    *,
    font_path: Path,
    font_size_px: int,
) -> float:
    if not line_words:
        return 0.0
    font = _load_font(font_path, font_size_px)
    return float(font.getlength(" ".join(line_words)))


def wrap_words_to_lines(
    words: list[str],
    *,
    font_path: Path,
    font_size_px: int,
    max_width_px: float,
    max_lines: int = 2,
) -> list[list[str]]:
    """Greedy-wrap words into up to ``max_lines`` lines within ``max_width_px``."""
    if not words:
        return []
    if max_lines < 1:
        max_lines = 1

    lines: list[list[str]] = []
    word_index = 0

    while word_index < len(words) and len(lines) < max_lines:
        current: list[str] = []
        while word_index < len(words):
            word = words[word_index]
            trial = current + [word]
            trial_w = line_width_px(
                trial,
                font_path=font_path,
                font_size_px=font_size_px,
            )
            if current and trial_w > max_width_px:
                break
            current.append(word)
            word_index += 1
        if current:
            lines.append(current)
        elif word_index < len(words):
            lines.append([words[word_index]])
            word_index += 1

    if word_index < len(words):
        if lines:
            lines[-1].extend(words[word_index:])
        else:
            lines.append(words[word_index:])

    return lines


def measure_word_offsets_in_line(
    line_words: list[str],
    *,
    font_path: Path,
    font_size_px: int,
) -> tuple[list[WordOffset], float]:
    """Measure each word's x-offset inside a space-joined line phrase."""
    if not line_words:
        return [], 0.0

    phrase = " ".join(line_words)
    font = _load_font(font_path, font_size_px)
    offsets: list[WordOffset] = []
    search_from = 0

    for word in line_words:
        idx = phrase.find(word, search_from)
        if idx < 0:
            raise ValueError(f"Word {word!r} not found in phrase {phrase!r}")
        prefix_w = float(font.getlength(phrase[:idx]))
        word_w = float(font.getlength(word))
        offsets.append(WordOffset(text=word, x_px=prefix_w, width_px=word_w))
        search_from = idx + len(word)

    return offsets, float(font.getlength(phrase))


def measure_phrase_word_offsets(
    words: list[str],
    *,
    font_path: Path,
    font_size_px: int,
    word_spacing_px: float = 8.0,
) -> list[WordOffset]:
    """Measure horizontal pixel offsets for each word in a single-line phrase."""
    del word_spacing_px
    offsets, _ = measure_word_offsets_in_line(
        words,
        font_path=font_path,
        font_size_px=font_size_px,
    )
    return offsets


def fit_caption_layout(
    words: list[str],
    *,
    font_path: Path,
    base_font_size: int,
    max_width_px: float,
    max_lines: int = 2,
    min_font_size: int = 12,
) -> tuple[list[list[str]], int]:
    """Wrap words into lines, shrinking font until each line fits ``max_width_px``."""
    font_size = base_font_size
    lines = wrap_words_to_lines(
        words,
        font_path=font_path,
        font_size_px=font_size,
        max_width_px=max_width_px,
        max_lines=max_lines,
    )

    while font_size > min_font_size and any(
        line_width_px(line, font_path=font_path, font_size_px=font_size) > max_width_px
        for line in lines
    ):
        font_size = max(min_font_size, int(font_size * 0.92))
        lines = wrap_words_to_lines(
            words,
            font_path=font_path,
            font_size_px=font_size,
            max_width_px=max_width_px,
            max_lines=max_lines,
        )

    return lines, font_size


def layout_caption_chunk(
    words: list[str],
    *,
    font_path: Path,
    base_font_size: int,
    max_width_px: float,
    max_lines: int = 2,
) -> tuple[list[CaptionLineLayout], int]:
    """Return wrapped line layouts and the font size used."""
    lines, font_size = fit_caption_layout(
        words,
        font_path=font_path,
        base_font_size=base_font_size,
        max_width_px=max_width_px,
        max_lines=max_lines,
    )
    layouts: list[CaptionLineLayout] = []
    for line_words in lines:
        offsets, line_width = measure_word_offsets_in_line(
            line_words,
            font_path=font_path,
            font_size_px=font_size,
        )
        layouts.append(
            CaptionLineLayout(
                words=line_words,
                line_width_px=line_width,
                word_offsets=offsets,
            )
        )
    return layouts, font_size


def phrase_total_width_px(
    words: list[str],
    *,
    font_path: Path,
    font_size_px: int,
    word_spacing_px: float = 8.0,
) -> float:
    del word_spacing_px
    _, width = measure_word_offsets_in_line(
        words,
        font_path=font_path,
        font_size_px=font_size_px,
    )
    return width
