"""Tests for final-resolution render (Phase 6)."""

from __future__ import annotations

from pathlib import Path

import pytest

from viral_editor.config import RenderConfig
from viral_editor.models import RenderPlan, SpeedSegment
from viral_editor.utils.ffmpeg import ffmpeg_available, run_ffmpeg, run_ffprobe_json
from viral_editor.video.final_render import (
    build_final_encode_args,
    build_final_filtergraph,
    plan_output_duration_s,
    render_final,
    verify_final_output,
)


def _sample_plan() -> RenderPlan:
    return RenderPlan(
        output_duration_s=4.0,
        speed_segments=[
            SpeedSegment(
                out_start_s=0.0,
                out_end_s=2.0,
                src_start_s=0.0,
                src_end_s=10.0,
                speed_factor=5.0,
                source_id="clip_a",
            ),
            SpeedSegment(
                out_start_s=2.0,
                out_end_s=4.0,
                src_start_s=10.0,
                src_end_s=20.0,
                speed_factor=5.0,
                source_id="clip_a",
            ),
        ],
    )


def _generate_test_clip(path: Path, duration_s: float) -> None:
    run_ffmpeg(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"testsrc=duration={duration_s}:size=320x240:rate=30",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration_s}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(path),
        ]
    )


def _generate_test_audio(path: Path, duration_s: float) -> None:
    run_ffmpeg(
        [
            "-y",
            "-f",
            "lavfi",
            "-i",
            f"sine=frequency=440:duration={duration_s}",
            "-c:a",
            "aac",
            str(path),
        ]
    )


def test_final_filtergraph_uses_render_config_resolution() -> None:
    render_cfg = RenderConfig()
    graph = build_final_filtergraph(
        _sample_plan(),
        render_cfg,
        clip_input_index={"clip_a": 0},
        clip_durations={"clip_a": 30.0},
    )
    assert "scale=1080:1920" in graph or "crop=1080:1920" in graph


def test_final_encode_args_locked_spec() -> None:
    render_cfg = RenderConfig()
    args = build_final_encode_args(render_cfg, audio_input_index=1)
    joined = " ".join(args)
    assert "-crf 18" in joined
    assert "-preset medium" in joined
    assert "-pix_fmt yuv420p" in joined
    assert "-r 60" in joined
    assert "-c:a aac" in joined
    assert "-b:a 192k" in joined
    assert "-movflags +faststart" in joined


def test_final_segment_continuity() -> None:
    plan = _sample_plan()
    segment_sum = sum(
        segment.out_end_s - segment.out_start_s for segment in plan.speed_segments
    )
    estimated = plan_output_duration_s(plan)
    assert abs(estimated - segment_sum) < 1.0 / 60.0
    assert abs(estimated - plan.output_duration_s) < 1.0 / 60.0


def test_render_duration_independent_of_loop_crossfade(monkeypatch) -> None:
    """Mux length comes from the render plan, not music loop crossfade settings."""
    from viral_editor.audio import loop_seam

    plan = _sample_plan()
    expected_duration_s = plan_output_duration_s(plan)
    assert expected_duration_s == 4.0

    for crossfade_s in (0.04, 0.12, 0.25, 0.5):
        monkeypatch.setattr(loop_seam, "DEFAULT_CROSSFADE_S", crossfade_s)
        assert plan_output_duration_s(plan) == expected_duration_s

        encode_args = build_final_encode_args(
            RenderConfig(),
            audio_input_index=1,
            duration_s=plan_output_duration_s(plan),
        )
        assert f"-t {expected_duration_s:.6f}" in " ".join(encode_args)


def test_final_render_without_title_omits_overlay() -> None:
    render_cfg = RenderConfig()
    graph = build_final_filtergraph(
        _sample_plan(),
        render_cfg,
        clip_input_index={"clip_a": 0},
        clip_durations={"clip_a": 30.0},
        title=None,
        title_ass_path=None,
        hook_text=None,
    )
    assert "drawtext" not in graph
    assert "ass=" not in graph


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_final_render_smoke_ffprobe(tmp_path: Path) -> None:
    clip_path = tmp_path / "clip.mp4"
    audio_path = tmp_path / "track.m4a"
    out_path = tmp_path / "final.mp4"
    _generate_test_clip(clip_path, 30.0)
    _generate_test_audio(audio_path, 8.0)

    plan = _sample_plan()
    render_cfg = RenderConfig()
    render_final(
        plan,
        render_cfg,
        clip_paths={"clip_a": clip_path},
        clip_durations={"clip_a": 30.0},
        audio_path=audio_path,
        out_path=out_path,
        music_start_s=0.0,
        music_end_s=8.0,
        temp_dir=tmp_path,
    )

    payload = run_ffprobe_json(["-show_entries", "format=duration", "-show_streams", str(out_path)])
    video = next(stream for stream in payload["streams"] if stream["codec_type"] == "video")
    audio = next(stream for stream in payload["streams"] if stream["codec_type"] == "audio")
    assert int(video["width"]) == 1080
    assert int(video["height"]) == 1920
    assert video["codec_name"] == "h264"
    assert audio["codec_name"] in ("aac", "mp4a")
    verify_final_output(
        out_path,
        render_cfg,
        expected_duration_s=plan_output_duration_s(plan),
    )
