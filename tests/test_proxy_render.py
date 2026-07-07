"""Tests for speed-ramp proxy filtergraph builder."""

from __future__ import annotations

import re

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
        "viral_editor.video.filter_builders.resolve_font_for_ffmpeg",
        lambda family: "C\\:/Windows/Fonts/arial.ttf",
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
    assert "slot0titled" not in graph
    assert "copy[motionv]" in graph
    assert "enable='between(t\\,0.000000\\,2.000000)'" in graph
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


def test_build_composite_filtergraph_hook_start_mask_and_spatial_fx(monkeypatch) -> None:
    from viral_editor.models import FxEvent

    monkeypatch.setattr(
        "viral_editor.video.filter_builders.resolve_font_for_ffmpeg",
        lambda family: "C\\:/Windows/Fonts/arial.ttf",
    )
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.5,
            src_start_s=8.0,
            src_end_s=10.0,
            speed_factor=0.8,
            source_id="clip_a",
        ),
        SpeedSegment(
            out_start_s=2.5,
            out_end_s=5.0,
            src_start_s=0.0,
            src_end_s=4.0,
            speed_factor=2.0,
            source_id="clip_b",
        ),
    ]
    fx_events = [
        FxEvent(timestamp_s=1.0, kind="zoom", magnitude=1.07, decay_frames=4),
        FxEvent(timestamp_s=2.0, kind="rotate", magnitude=1.2, decay_frames=4),
    ]
    graph = build_composite_filtergraph(
        segments,
        ["cut", "cut"],
        clip_input_index={"clip_a": 0, "clip_b": 1},
        clip_durations={"clip_a": 10.0, "clip_b": 12.0},
        hook_text="Hook",
        segment_roles=["hook_start", "clip"],
        hook_start_mask="vignette",
        segment_transforms=[(0, "contain", None), (90, "cover", None)],
        fx_events=fx_events,
        fx_seed=7,
        fx_intensity=1.0,
    )
    assert "vignette=angle=PI/5" in graph
    assert "concat=n=2:v=1:a=0[composed]" not in graph
    assert "drawtext" in graph
    assert "slot0titled" not in graph
    assert "copy[motionv]" in graph
    assert "w='trunc(iw*(" in graph
    assert "rotate=enable='between(t," in graph
    assert "eval=frame" in graph
    assert re.search(r"rotate=[^\]]*eval=frame", graph) is None
    assert "rotate=enable='between(t," in graph
    assert "[outv]" in graph


def test_build_composite_filtergraph_translate_pan() -> None:
    from viral_editor.models import FxEvent

    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=5.0,
            src_start_s=0.0,
            src_end_s=5.0,
            speed_factor=1.0,
            source_id="clip_a",
        ),
    ]
    fx_events = [
        FxEvent(
            timestamp_s=1.0,
            kind="translate",
            magnitude=0.9,
            decay_frames=4,
            direction=1,
        ),
    ]
    graph = build_composite_filtergraph(
        segments,
        ["cut"],
        clip_input_index={"clip_a": 0},
        clip_durations={"clip_a": 10.0},
        fx_events=fx_events,
        fx_seed=7,
        fx_intensity=1.0,
    )
    assert "crop=360:640:x='(iw-ow)/2+(if(between(t," in graph
    assert graph.count("trunc(iw*1.150000)") == 1
    assert "rotate=" not in graph
    assert "[outv]" in graph


def test_apply_spatial_fx_chain_applies_all_events() -> None:
    from viral_editor.models import FxEvent
    from viral_editor.video.filter_builders import apply_spatial_fx_chain

    fx_events = [
        FxEvent(timestamp_s=index * 0.5, kind="translate", magnitude=0.9, decay_frames=6, direction=1)
        for index in range(30)
    ] + [
        FxEvent(timestamp_s=20.0, kind="zoom", magnitude=1.07, decay_frames=4),
    ]
    parts: list[str] = []
    apply_spatial_fx_chain(
        parts,
        "[bodyv]",
        fx_events,
        width=360,
        height=640,
        fps=30,
        seed=7,
        intensity=1.0,
    )
    graph = ";".join(parts)
    assert graph.count("if(between(t,") >= 30
    assert "w='trunc(iw*(" in graph
    assert "blend=" not in graph


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_apply_spatial_fx_chain_tail_batch_pan_has_headroom() -> None:
    import tempfile
    from pathlib import Path

    from viral_editor.models import FxEvent
    from viral_editor.utils.ffmpeg import run_ffmpeg
    from viral_editor.video.filter_builders import (
        PAN_EXPR_BATCH_SIZE,
        apply_spatial_fx_chain,
    )

    early = [
        FxEvent(timestamp_s=1.0 + index * 0.5, kind="translate", magnitude=0.9, decay_frames=6, direction=1)
        for index in range(PAN_EXPR_BATCH_SIZE)
    ]
    tail = [
        FxEvent(timestamp_s=45.0 + index * 0.5, kind="translate", magnitude=0.9, decay_frames=6, direction=-1)
        for index in range(4)
    ]
    parts = ["nullsrc=s=360x640:d=50,format=yuv420p[bodyv]"]
    apply_spatial_fx_chain(
        parts,
        "[bodyv]",
        early + tail,
        width=360,
        height=640,
        fps=30,
        seed=7,
        intensity=1.0,
        output_label="outv",
    )
    graph = ";".join(parts)
    assert graph.count("blend=all_expr='if(") >= 1
    assert graph.count("trunc(iw*1.150000)") == 1
    out_path = Path(tempfile.gettempdir()) / "spatial_fx_tail_batch_pan.mp4"
    run_ffmpeg(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc=duration=50:size=360x640:rate=30",
            "-filter_complex",
            graph,
            "-map",
            "[outv]",
            "-t",
            "50",
            str(out_path),
        ]
    )
    assert out_path.is_file()
    assert out_path.stat().st_size > 0


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_apply_spatial_fx_chain_large_translate_batch_ffmpeg() -> None:
    import tempfile
    from pathlib import Path

    from viral_editor.models import FxEvent
    from viral_editor.utils.ffmpeg import run_ffmpeg
    from viral_editor.video.filter_builders import apply_spatial_fx_chain

    fx_events = [
        FxEvent(
            timestamp_s=index * 0.5 + 1.0,
            kind="translate",
            magnitude=0.9,
            decay_frames=6,
            direction=1 if index % 2 == 0 else -1,
        )
        for index in range(101)
    ]
    parts = ["nullsrc=s=360x640:d=20,format=yuv420p[bodyv]"]
    apply_spatial_fx_chain(
        parts,
        "[bodyv]",
        fx_events,
        width=360,
        height=640,
        fps=30,
        seed=7,
        intensity=1.0,
        output_label="outv",
    )
    filtergraph = ";".join(parts)
    out_path = Path(tempfile.gettempdir()) / "spatial_fx_large_translate.mp4"
    run_ffmpeg(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=360x640:d=20",
            "-filter_complex",
            filtergraph,
            "-map",
            "[outv]",
            "-t",
            "3",
            str(out_path),
        ]
    )
    assert out_path.is_file()
    assert out_path.stat().st_size > 0


def test_build_composite_filtergraph_translate_pan_many_beats() -> None:
    from viral_editor.models import FxEvent

    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=5.0,
            src_start_s=0.0,
            src_end_s=5.0,
            speed_factor=1.0,
            source_id="clip_a",
        ),
    ]
    fx_events = [
        FxEvent(
            timestamp_s=1.0,
            kind="translate",
            magnitude=0.9,
            decay_frames=6,
            direction=1,
        ),
        FxEvent(
            timestamp_s=1.5,
            kind="translate",
            magnitude=0.85,
            decay_frames=6,
            direction=-1,
        ),
        FxEvent(
            timestamp_s=2.0,
            kind="translate",
            magnitude=0.9,
            decay_frames=6,
            direction=1,
        ),
    ]
    graph = build_composite_filtergraph(
        segments,
        ["cut"],
        clip_input_index={"clip_a": 0},
        clip_durations={"clip_a": 10.0},
        fx_events=fx_events,
        fx_seed=7,
        fx_intensity=1.0,
    )
    assert graph.count("trunc(iw*1.150000)") == 1
    assert graph.count("if(between(t,") >= 3
    assert "[outv]" in graph


def test_composite_output_duration_uses_segment_timeline() -> None:
    from viral_editor.video.proxy_render import composite_output_duration_s

    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=5.0,
            src_start_s=0.0,
            src_end_s=5.0,
            speed_factor=1.0,
        ),
    ]
    assert composite_output_duration_s(segments) == pytest.approx(5.0)


def test_storyboard_mux_duration_ignores_xfade_overlap() -> None:
    from viral_editor.video.filter_builders import (
        composite_output_duration_s,
        storyboard_mux_duration_s,
    )

    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=2.0,
            speed_factor=1.0,
            source_id="clip_a",
        ),
        SpeedSegment(
            out_start_s=2.0,
            out_end_s=5.0,
            src_start_s=0.0,
            src_end_s=3.0,
            speed_factor=1.0,
            source_id="clip_b",
        ),
    ]
    transitions = ["cut", "xfade"]
    assert storyboard_mux_duration_s(segments) == pytest.approx(5.0)
    assert composite_output_duration_s(segments, transitions=transitions) == pytest.approx(4.75)


def test_build_composite_filtergraph_pads_video_to_storyboard_duration_for_captions() -> None:
    from viral_editor.models import CaptionChunk, CaptionWord, CaptionStyle, SpeedSegment
    from viral_editor.video.filter_builders import build_composite_filtergraph

    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=2.0,
            speed_factor=1.0,
            source_id="clip_a",
        ),
        SpeedSegment(
            out_start_s=2.0,
            out_end_s=5.0,
            src_start_s=0.0,
            src_end_s=3.0,
            speed_factor=1.0,
            source_id="clip_b",
        ),
    ]
    chunks = {
        "slot0": [
            CaptionChunk(
                words=[CaptionWord(text="late", start_s=4.5, end_s=4.9)],
                start_s=4.5,
                end_s=4.9,
            )
        ]
    }
    graph = build_composite_filtergraph(
        segments,
        ["cut", "xfade"],
        clip_input_index={"clip_a": 0, "clip_b": 1},
        clip_durations={"clip_a": 10.0, "clip_b": 10.0},
        caption_chunks_by_slot=chunks,
        caption_style=CaptionStyle(),
        slot_ids=["slot0", "slot1"],
        slot_offsets={"slot0": 0.0, "slot1": 2.0},
    )
    assert "tpad=stop_mode=clone:stop_duration=0.250000" in graph
    assert "between(t\\,4.500000\\,4.900000)" in graph


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


def test_build_composite_filtergraph_spatial_crop_letterbox() -> None:
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
        clip_transforms={"clip_a": (0, "contain", (0.0, -0.1, 1.0, 1.2))},
    )
    assert "pad=" in graph
    assert "color=black" in graph
    assert "scale=360:640" in graph


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
