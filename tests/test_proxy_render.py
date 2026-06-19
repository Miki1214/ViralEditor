"""Tests for speed-ramp proxy filtergraph builder."""

from __future__ import annotations

import pytest

from viral_editor.models import SpeedRampPlan, SpeedSegment
from viral_editor.utils.ffmpeg import ffmpeg_available
from viral_editor.video.proxy_render import build_proxy_filtergraph, render_speed_proxy


def _sample_plan() -> SpeedRampPlan:
    return SpeedRampPlan(
        style="drop_sync",
        output_duration_s=4.0,
        src_duration_s=20.0,
        budget_policy="scale",
        segments=[
            SpeedSegment(
                out_start_s=0.0,
                out_end_s=2.0,
                src_start_s=0.0,
                src_end_s=10.0,
                speed_factor=5.0,
            ),
            SpeedSegment(
                out_start_s=2.0,
                out_end_s=4.0,
                src_start_s=10.0,
                src_end_s=20.0,
                speed_factor=5.0,
            ),
        ],
    )


def test_build_proxy_filtergraph_contains_trim_and_concat() -> None:
    graph = build_proxy_filtergraph(_sample_plan(), scale=(360, 640))
    assert "trim=start=0.000000:end=10.000000" in graph
    assert "concat=n=2:v=1:a=0[outv]" in graph
    assert "scale=360:640" in graph


def test_build_proxy_filtergraph_multi_input_source_id() -> None:
    plan = SpeedRampPlan(
        style="drop_sync",
        output_duration_s=2.0,
        src_duration_s=10.0,
        budget_policy="scale",
        segments=[
            SpeedSegment(
                out_start_s=0.0,
                out_end_s=1.0,
                src_start_s=1.0,
                src_end_s=3.0,
                speed_factor=2.0,
                source_id="clip_a",
            ),
            SpeedSegment(
                out_start_s=1.0,
                out_end_s=2.0,
                src_start_s=0.0,
                src_end_s=2.0,
                speed_factor=2.0,
                source_id="clip_b",
            ),
        ],
    )
    graph = build_proxy_filtergraph(
        plan,
        clip_input_index={"clip_a": 0, "clip_b": 1},
        clip_durations={"clip_a": 5.0, "clip_b": 6.0},
    )
    assert "[0:v]trim=start=1.000000:end=3.000000" in graph
    assert "[1:v]trim=start=0.000000:end=2.000000" in graph


def test_build_proxy_filtergraph_empty_plan() -> None:
    graph = build_proxy_filtergraph(
        SpeedRampPlan(output_duration_s=0.0, src_duration_s=1.0),
    )
    assert "nullsrc" in graph


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_render_speed_proxy_raises_without_real_media(tmp_path, monkeypatch) -> None:
    from viral_editor.utils.ffmpeg import FFmpegError

    def _fail(_command):
        raise FFmpegError("missing input", command=["ffmpeg"], stderr="No such file")

    monkeypatch.setattr("viral_editor.video.proxy_render.run_ffmpeg", _fail)
    video = tmp_path / "missing.mp4"
    audio = tmp_path / "missing.mp3"
    out = tmp_path / "preview.mp4"
    with pytest.raises(RuntimeError, match="Speed proxy render failed"):
        render_speed_proxy(
            audio,
            _sample_plan(),
            video_path=video,
            music_start_s=0.0,
            music_end_s=4.0,
            out_path=out,
        )
