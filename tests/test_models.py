"""Round-trip serialization tests for shared domain models."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from viral_editor.models import (
    AudioTimeline,
    BoxSpec,
    ClipInput,
    ClipReel,
    EmphasisSpec,
    FxEvent,
    MediaInfo,
    ReelEntry,
    RenderPlan,
    SafeRect,
    SpeedSegment,
    TeaserSpec,
    TimeWindow,
    TitleSpec,
    Transient,
    read_artifact,
    write_artifact,
)
from viral_editor.ingest.loader import IngestResult


def test_media_info_round_trip() -> None:
    original = MediaInfo(
        path=Path("assets/timelapse.mp4"),
        duration_s=30.0,
        has_video=True,
        width=1920,
        height=1080,
        fps=29.97,
        r_frame_rate_raw="30000/1001",
        codec_name="h264",
    )
    restored = MediaInfo.model_validate_json(original.model_dump_json())
    assert restored == original


def test_audio_timeline_round_trip() -> None:
    original = AudioTimeline(
        global_bpm=128.0,
        audio_duration_seconds=32.41,
        sample_rate=44100,
        transients=[
            Transient(timestamp_ms=1180, amplitude_normalized=0.88, type="percussive"),
            Transient(timestamp_ms=4720, amplitude_normalized=0.99, type="drop"),
        ],
    )
    restored = AudioTimeline.model_validate_json(original.model_dump_json())
    assert restored == original


def test_clip_models_round_trip() -> None:
    clip = ClipInput(
        id="clip_0",
        path=Path("input/a.mp4"),
        order=0,
        role="hook",
        crop_start_s=1.0,
        crop_end_s=4.0,
    )
    restored_clip = ClipInput.model_validate_json(clip.model_dump_json())
    assert restored_clip == clip

    reel = ClipReel(
        entries=[
            ReelEntry(
                clip_id="clip_0",
                path=Path("input/a.mp4"),
                reel_start_s=0.0,
                reel_end_s=3.0,
                src_start_s=1.0,
                src_end_s=4.0,
                is_hook_loop=False,
            )
        ],
        reel_duration_s=3.0,
    )
    assert reel.clip_boundaries_s() == []
    restored_reel = ClipReel.model_validate_json(reel.model_dump_json())
    assert restored_reel == reel


def test_speed_segment_round_trip() -> None:
    original = SpeedSegment(
        out_start_s=4.5,
        out_end_s=4.9,
        src_start_s=30.1,
        src_end_s=30.5,
        speed_factor=1.0,
        source_id="clip_0",
    )
    restored = SpeedSegment.model_validate_json(original.model_dump_json())
    assert restored == original


def test_fx_event_round_trip() -> None:
    original = FxEvent(timestamp_s=4.72, kind="zoom", magnitude=1.07, decay_frames=4)
    restored = FxEvent.model_validate_json(original.model_dump_json())
    assert restored == original


def test_teaser_spec_round_trip() -> None:
    original = TeaserSpec(
        src_start_s=28.5,
        src_end_s=30.0,
        out_duration_s=2.5,
        mask="vignette",
    )
    restored = TeaserSpec.model_validate_json(original.model_dump_json())
    assert restored == original


def test_title_spec_round_trip() -> None:
    original = TitleSpec(
        lines=["I built this in", "30 DAYS"],
        font="Montserrat Black",
        size_px=96,
        fill="#FFFFFF",
        emphasis=EmphasisSpec(words=["30", "days"], color="#FFD700"),
        box=BoxSpec(color="rgba(0,0,0,0.85)", padding_px=24, radius_px=16),
        safe_rect=SafeRect(x=108, y=192, w=864, h=1536),
        window_s=TimeWindow(start=0.0, end=2.5),
    )
    restored = TitleSpec.model_validate_json(original.model_dump_json())
    assert restored == original


def test_render_plan_round_trip() -> None:
    original = RenderPlan(
        output_duration_s=32.41,
        speed_segments=[
            SpeedSegment(
                out_start_s=0.0,
                out_end_s=1.0,
                src_start_s=0.0,
                src_end_s=10.0,
                speed_factor=10.0,
            )
        ],
        teaser=TeaserSpec(
            src_start_s=28.5,
            src_end_s=30.0,
            out_duration_s=2.5,
            mask="dir_blur",
        ),
        fx_events=[FxEvent(timestamp_s=1.0, kind="rotate", magnitude=1.2, decay_frames=4)],
    )
    restored = RenderPlan.model_validate_json(original.model_dump_json())
    assert restored == original


def test_ingest_result_round_trip() -> None:
    original = IngestResult(
        video=MediaInfo(
            path=Path("assets/timelapse.mp4"),
            duration_s=30.0,
            has_video=True,
            width=1920,
            height=1080,
            fps=30.0,
        ),
        audio=MediaInfo(
            path=Path("assets/track.mp3"),
            duration_s=32.41,
            has_audio=True,
            sample_rate=44100,
            channels=2,
        ),
        output_duration_s=32.41,
    )
    restored = IngestResult.model_validate_json(original.model_dump_json())
    assert restored == original


def test_write_and_read_artifact(temp_artifacts_dir: Path) -> None:
    timeline = AudioTimeline(
        global_bpm=120.0,
        audio_duration_seconds=10.0,
        sample_rate=48000,
    )
    path = write_artifact(timeline, "audio_timeline", temp_artifacts_dir)
    assert path.name == "audio_timeline.json"
    assert read_artifact(AudioTimeline, path) == timeline


def test_domain_models_reject_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Transient(
            timestamp_ms=100,
            amplitude_normalized=0.5,
            type="percussive",
            extra_field="nope",  # type: ignore[call-arg]
        )
