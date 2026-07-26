"""Verify filter chain uses per-word y tops for leading short word."""
from __future__ import annotations

from viral_editor.models import CaptionChunk, CaptionWord, CaptionStyle, SpeedSegment
from viral_editor.utils.ffmpeg import ffmpeg_available
from viral_editor.utils.fonts import resolve_font_path
from viral_editor.utils.text_metrics import layout_caption_chunk
from viral_editor.video.filter_builders import (
    _base_font_size,
    _caption_block_y_base_px,
    _caption_line_spacing_px,
    _max_caption_width_px,
    _measure_karaoke_word_y_tops_px,
    build_caption_filter_chain,
)


def test_karaoke_leading_word_uses_higher_y_than_line_top() -> None:
  if not ffmpeg_available():
      import pytest

      pytest.skip("ffmpeg not available")

  font_path = resolve_font_path("Bebas Neue")
  if font_path is None:
      import pytest

      pytest.skip("No font available for karaoke y-top test")

  style = CaptionStyle(
      fill_color="#00FFCC",
      emphasis_color="#FF00AA",
      position="bottom",
      karaoke_enabled=True,
      font_family="Bebas Neue",
      outline_enabled=True,
      box_enabled=False,
  )
  words = ["sees", "the", "ghost", "him."]
  chunk_words = [
      CaptionWord(text=w, start_s=i * 0.2, end_s=(i + 1) * 0.2) for i, w in enumerate(words)
  ]
  width, height = 360, 640
  fontsize = _base_font_size(style, height)
  line_spacing = _caption_line_spacing_px(fontsize)
  block_y = _caption_block_y_base_px(
      style,
      height=height,
      fontsize=fontsize,
      num_lines=2,
      line_spacing=line_spacing,
  )
  layouts, fontsize = layout_caption_chunk(
      words,
      font_path=font_path,
      base_font_size=fontsize,
      max_width_px=_max_caption_width_px(width, style),
      max_lines=2,
  )
  phrase = " ".join(layouts[0].words)
  from viral_editor.utils.fonts import resolve_font_for_ffmpeg

  tops = _measure_karaoke_word_y_tops_px(
      phrase,
      layouts[0].word_offsets,
      fontfile=resolve_font_for_ffmpeg("Bebas Neue") or "",
      fontsize=fontsize,
      border_px=max(2, fontsize // 14),
      line_y=block_y,
      line_width_px=layouts[0].line_width_px,
      frame_width=width,
      frame_height=height,
      fill_color=style.fill_color,
  )
  assert tops[0] > block_y
  assert abs(tops[1] - block_y) < 0.01

  parts: list[str] = []
  build_caption_filter_chain(
      parts,
      "[slot0norm]",
      chunks_by_slot={"slot0": [CaptionChunk(words=chunk_words, start_s=0.0, end_s=1.0)]},
      segments=[
          SpeedSegment(
              out_start_s=0.0,
              out_end_s=2.0,
              src_start_s=0.0,
              src_end_s=2.0,
              speed_factor=1.0,
              source_id="clip_a",
          )
      ],
      slot_ids=["slot0"],
      style=style,
      label_prefix="cap",
      width=width,
      height=height,
  )
  graph = ";".join(parts)
  assert f":y={tops[0]:.2f}" in graph
  assert f":y={block_y:.2f}" in graph
