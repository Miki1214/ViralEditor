"""Tests for multi-clip virtual reel builder."""

from __future__ import annotations

from pathlib import Path

import pytest

from viral_editor.config import SpeedRampConfig
from viral_editor.models import ClipInput, MediaInfo, SpeedSegment
from viral_editor.video.clip_reel import build_reel, localize_segments


def _media(duration: float, clip_id: str = "x") -> MediaInfo:
    return MediaInfo(path=Path(f"/fake/{clip_id}.mp4"), duration_s=duration, has_video=True)


def _clip(
    clip_id: str,
    *,
    order: int,
    role: str = "clip",
    crop_start: float | None = None,
    crop_end: float | None = None,
    included: bool = True,
) -> ClipInput:
    return ClipInput(
        id=clip_id,
        path=Path(f"/fake/{clip_id}.mp4"),
        order=order,
        included=included,
        role=role,  # type: ignore[arg-type]
        crop_start_s=crop_start,
        crop_end_s=crop_end,
    )


def test_build_reel_orders_clip_roles() -> None:
    clips = [
        _clip("b", order=1),
        _clip("a", order=0),
        _clip("f", order=2, role="filler"),
        _clip("h", order=3, role="hook"),
    ]
    media = {
        "a": _media(10.0, "a"),
        "b": _media(8.0, "b"),
        "f": _media(5.0, "f"),
        "h": _media(4.0, "h"),
    }
    config = SpeedRampConfig(s_min=1.0)

    reel = build_reel(clips, media, body_output_duration_s=12.0, speed_config=config)

    assert [entry.clip_id for entry in reel.entries[:2]] == ["a", "b"]
    assert reel.entries[0].reel_start_s == pytest.approx(0.0)
    assert reel.entries[0].reel_end_s == pytest.approx(10.0)
    assert reel.entries[1].reel_start_s == pytest.approx(10.0)
    assert reel.reel_duration_s >= 12.0


def test_build_reel_fills_with_filler_then_hook_loop() -> None:
    clips = [
        _clip("main", order=0),
        _clip("hook", order=1, role="hook"),
    ]
    media = {
        "main": _media(3.0, "main"),
        "hook": _media(2.0, "hook"),
    }
    config = SpeedRampConfig(s_min=1.0)

    reel = build_reel(clips, media, body_output_duration_s=10.0, speed_config=config)

    assert reel.reel_duration_s >= 10.0
    assert reel.entries[0].clip_id == "main"
    assert any(entry.is_hook_loop and entry.clip_id == "hook" for entry in reel.entries)


def test_localize_segments_splits_at_clip_boundaries() -> None:
    clips = [
        _clip("a", order=0, crop_end=5.0),
        _clip("b", order=1, crop_end=4.0),
    ]
    media = {"a": _media(10.0, "a"), "b": _media(8.0, "b")}
    reel = build_reel(clips, media, body_output_duration_s=9.0, speed_config=SpeedRampConfig())

    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=9.0,
            src_start_s=0.0,
            src_end_s=9.0,
            speed_factor=1.0,
        )
    ]
    localized = localize_segments(segments, reel)

    assert len(localized) == 2
    assert localized[0].source_id == "a"
    assert localized[1].source_id == "b"
    assert localized[0].src_end_s == pytest.approx(5.0)
    assert localized[1].src_start_s == pytest.approx(0.0)
    assert localized[1].src_end_s == pytest.approx(4.0)


def test_localize_segments_stops_at_reel_end() -> None:
    clips = [_clip("a", order=0)]
    media = {"a": _media(30.0, "a")}
    reel = build_reel(clips, media, body_output_duration_s=50.0, speed_config=SpeedRampConfig())
    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=50.0,
            src_start_s=0.0,
            src_end_s=50.0,
            speed_factor=1.0,
        )
    ]
    localized = localize_segments(segments, reel)
    assert localized
    assert localized[-1].src_end_s <= reel.reel_duration_s + 1e-6


def test_build_reel_is_deterministic() -> None:
    clips = [_clip("a", order=0), _clip("b", order=1)]
    media = {"a": _media(6.0), "b": _media(6.0)}
    kwargs = dict(
        clips=clips,
        clip_media=media,
        body_output_duration_s=8.0,
        speed_config=SpeedRampConfig(),
    )
    first = build_reel(**kwargs)
    second = build_reel(**kwargs)
    assert first.model_dump() == second.model_dump()
