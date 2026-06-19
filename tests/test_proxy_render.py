"""Tests for speed-ramp proxy filtergraph builder."""

from __future__ import annotations

import pytest

from viral_editor.models import SpeedRampPlan, SpeedSegment
from viral_editor.utils.ffmpeg import ffmpeg_available
from viral_editor.video.proxy_render import (
    build_composite_filtergraph,
    build_proxy_filtergraph,
    render_speed_proxy,
)


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


def test_build_composite_filtergraph_xfade_and_drawtext(monkeypatch) -> None:
    monkeypatch.setattr(
        "viral_editor.video.proxy_render.resolve_drawtext_fontfile",
        lambda: "C\\:/Windows/Fonts/arial.ttf",
    )
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=4.0,
            speed_factor=2.0,
            source_id="clip_a",
        ),
        SpeedSegment(
            out_start_s=2.0,
            out_end_s=5.0,
            src_start_s=0.0,
            src_end_s=6.0,
            speed_factor=2.0,
            source_id="clip_b",
        ),
    ]
    graph = build_composite_filtergraph(
        segments,
        ["cut", "xfade"],
        clip_input_index={"clip_a": 0, "clip_b": 1},
        clip_durations={"clip_a": 10.0, "clip_b": 12.0},
        hook_text="Hello hook",
    )
    assert "drawtext" in graph
    assert "fontfile='C\\:/Windows/Fonts/arial.ttf'" in graph
    assert "xfade=transition=fade" in graph
    assert "fps=30" in graph
    assert "[outv]" in graph
    graph = build_proxy_filtergraph(
        SpeedRampPlan(output_duration_s=0.0, src_duration_s=1.0),
    )
    assert "nullsrc" in graph


def test_build_composite_filtergraph_rotation_and_cover() -> None:
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=4.0,
            speed_factor=2.0,
            source_id="clip_a",
        ),
    ]
    graph = build_composite_filtergraph(
        segments,
        ["cut"],
        clip_input_index={"clip_a": 0},
        clip_durations={"clip_a": 10.0},
        clip_transforms={"clip_a": (90, "contain", (0.1, 0.2, 0.5, 0.8))},
    )
    assert "transpose=1" in graph
    assert "crop=iw*0.500000:ih*0.800000:iw*0.100000:ih*0.200000" in graph
    assert "scale=360:640" in graph


def test_build_composite_filtergraph_spatial_crop() -> None:
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=4.0,
            speed_factor=2.0,
            source_id="clip_a",
        ),
    ]
    graph = build_composite_filtergraph(
        segments,
        ["cut"],
        clip_input_index={"clip_a": 0},
        clip_durations={"clip_a": 10.0},
        clip_transforms={"clip_a": (0, "contain", (0.0, 0.0, 0.5625, 1.0))},
    )
    assert "crop=iw*0.562500:ih*1.000000:iw*0.000000:ih*0.000000" in graph


def test_render_composite_uses_looped_seam_audio(tmp_path, monkeypatch) -> None:
    from viral_editor.video.proxy_render import render_composite

    loop_calls: list[tuple[float, float]] = []

    def _fake_loop(
        audio_path,
        *,
        start_s,
        end_s,
        temp_dir,
    ):
        loop_calls.append((start_s, end_s))
        loop_wav = temp_dir / "previews" / "loop.wav"
        loop_wav.parent.mkdir(parents=True, exist_ok=True)
        loop_wav.write_bytes(b"RIFF")
        return loop_wav

    captured: list[list[str]] = []

    def _fake_ffmpeg(command):
        captured.append(command)

    monkeypatch.setattr(
        "viral_editor.video.proxy_render.ensure_loop_seam_audio",
        _fake_loop,
    )
    monkeypatch.setattr("viral_editor.video.proxy_render.run_ffmpeg", _fake_ffmpeg)

    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=4.0,
            speed_factor=2.0,
            source_id="clip_a",
        ),
    ]
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"mp4")
    audio = tmp_path / "audio.mp3"
    audio.write_bytes(b"mp3")
    out = tmp_path / "out.mp4"

    render_composite(
        audio,
        segments,
        ["cut"],
        clip_paths={"clip_a": clip},
        clip_durations={"clip_a": 10.0},
        music_start_s=1.0,
        music_end_s=9.0,
        out_path=out,
        temp_dir=tmp_path,
    )

    assert loop_calls == [(1.0, 9.0)]
    assert captured
    assert "-stream_loop" in captured[0]
    assert "-1" in captured[0]


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_render_speed_proxy_raises_without_real_media(tmp_path, monkeypatch) -> None:
    from viral_editor.utils.ffmpeg import FFmpegError

    loop_wav = tmp_path / "loop.wav"
    loop_wav.write_bytes(b"wav")
    monkeypatch.setattr(
        "viral_editor.video.proxy_render.ensure_loop_seam_audio",
        lambda *args, **kwargs: loop_wav,
    )

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
