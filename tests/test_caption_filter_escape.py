"""Regression tests for drawtext escaping in caption filters."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from viral_editor.models import CaptionChunk, CaptionStyle, CaptionWord, SpeedSegment
from viral_editor.utils.ffmpeg import ffmpeg_available, resolve_ffmpeg_binary, run_ffmpeg
from viral_editor.video.filter_builders import build_composite_filtergraph


def test_caption_filtergraph_survives_apostrophe_in_phrase(monkeypatch) -> None:
    monkeypatch.setattr(
        "viral_editor.video.filter_builders.resolve_font_for_ffmpeg",
        lambda family: "C\\:/Windows/Fonts/arial.ttf",
    )
    style = CaptionStyle(karaoke_enabled=False)
    chunks = {
        "slot0": [
            CaptionChunk(
                words=[CaptionWord(text="don't", start_s=0.0, end_s=0.5)],
                start_s=0.0,
                end_s=0.5,
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
    graph = build_composite_filtergraph(
        segments,
        ["cut"],
        clip_input_index={"clip_a": 0},
        clip_durations={"clip_a": 10.0},
        caption_chunks_by_slot=chunks,
        caption_style=style,
        slot_ids=["slot0"],
    )
    assert "don''t" in graph
    assert "enable='between(t\\," in graph


def test_caption_filtergraph_renders_with_apostrophe() -> None:
    if not ffmpeg_available():
        return

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

    style = CaptionStyle(karaoke_enabled=False)
    chunks = {
        "slot0": [
            CaptionChunk(
                words=[CaptionWord(text="don't", start_s=0.0, end_s=1.0)],
                start_s=0.0,
                end_s=1.0,
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
    graph = build_composite_filtergraph(
        segments,
        ["cut"],
        clip_input_index={"clip_a": 0},
        clip_durations={"clip_a": 10.0},
        caption_chunks_by_slot=chunks,
        caption_style=style,
        slot_ids=["slot0"],
    )
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
