"""Regression tests for drawtext escaping in caption filters."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

import pytest

from viral_editor.models import CaptionChunk, CaptionStyle, CaptionWord, SpeedSegment
from viral_editor.utils.ffmpeg import escape_drawtext_text, ffmpeg_available, resolve_ffmpeg_binary, run_ffmpeg
from viral_editor.video.filter_builders import build_composite_filtergraph


@pytest.mark.parametrize(
    ("text", "escaped"),
    [
        ("don't", "don''t"),
        ("50% off", "50% off"),
        ("100%", "100%"),
        ("a:b", "a\\:b"),
        ("one, two; [ok]", "one, two; [ok]"),
        ("back\\slash", "back\\\\slash"),
        ("#hash @user $100", "#hash @user $100"),
        ("%{pts}", "%{pts}"),
    ],
)
def test_escape_drawtext_text_handles_special_characters(text: str, escaped: str) -> None:
    assert escape_drawtext_text(text) == escaped


def _composite_graph_for_phrase(phrase: str, *, karaoke: bool = False) -> str:
    style = CaptionStyle(karaoke_enabled=karaoke)
    chunks = {
        "slot0": [
            CaptionChunk(
                words=[
                    CaptionWord(text=word, start_s=index * 0.25, end_s=(index + 1) * 0.25)
                    for index, word in enumerate(phrase.split())
                ],
                start_s=0.0,
                end_s=max(0.5, 0.25 * len(phrase.split())),
            )
        ]
    }
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=2.0,
            speed_factor=1.0,
            source_id="clip_a",
        )
    ]
    return build_composite_filtergraph(
        segments,
        ["cut"],
        clip_input_index={"clip_a": 0},
        clip_durations={"clip_a": 10.0},
        caption_chunks_by_slot=chunks,
        caption_style=style,
        slot_ids=["slot0"],
    )


def test_caption_filtergraph_survives_apostrophe_in_phrase(monkeypatch) -> None:
    monkeypatch.setattr(
        "viral_editor.video.filter_builders.resolve_font_for_ffmpeg",
        lambda family: "C\\:/Windows/Fonts/arial.ttf",
    )
    graph = _composite_graph_for_phrase("don't")
    assert "don''t" in graph
    assert "expansion=none" in graph
    assert "enable='between(t\\," in graph


def test_caption_filtergraph_survives_percent_and_colon(monkeypatch) -> None:
    monkeypatch.setattr(
        "viral_editor.video.filter_builders.resolve_font_for_ffmpeg",
        lambda family: "C\\:/Windows/Fonts/arial.ttf",
    )
    graph = _composite_graph_for_phrase("don't: 50% off")
    assert "don''t\\: 50% off" in graph
    assert "expansion=none" in graph


def test_caption_filtergraph_renders_special_characters(monkeypatch) -> None:
    if not ffmpeg_available():
        pytest.skip("ffmpeg not available")

    monkeypatch.setattr(
        "viral_editor.video.filter_builders.resolve_font_for_ffmpeg",
        lambda family: "C\\:/Windows/Fonts/arial.ttf",
    )

    tmpdir = Path(tempfile.mkdtemp())
    clip = tmpdir / "clip.mp4"
    run_ffmpeg(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=5:size=320x240:rate=30",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(clip),
        ]
    )

    graph = _composite_graph_for_phrase("don't: 50% off")
    ffmpeg = resolve_ffmpeg_binary("ffmpeg")
    assert ffmpeg is not None
    result = subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(clip),
            "-filter_complex",
            graph,
            "-map",
            "[outv]",
            "-frames:v",
            "1",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr[-500:]
