"""Tests for the frame-0 teaser planner."""

from __future__ import annotations

from pathlib import Path

import pytest

from viral_editor.config import TeaserConfig
from viral_editor.models import ClipInput, MediaInfo
from viral_editor.video.teaser import build_teaser_spec, teaser_body_output_duration


def _video(duration_s: float) -> MediaInfo:
    return MediaInfo(
        path=Path("assets/timelapse.mp4"),
        duration_s=duration_s,
        has_video=True,
        fps=30.0,
    )


def test_teaser_tail_range_for_default_fraction() -> None:
    spec = build_teaser_spec(_video(30.0), TeaserConfig())
    assert spec.src_start_s == pytest.approx(28.5)
    assert spec.src_end_s == pytest.approx(30.0)
    assert spec.out_duration_s == pytest.approx(2.5)
    assert spec.mask == "vignette"


def test_teaser_respects_custom_tail_fraction_and_mask() -> None:
    spec = build_teaser_spec(
        _video(20.0),
        TeaserConfig(tail_fraction=0.1, duration_s=3.0, mask="dir_blur"),
    )
    assert spec.src_start_s == pytest.approx(18.0)
    assert spec.src_end_s == pytest.approx(20.0)
    assert spec.out_duration_s == pytest.approx(3.0)
    assert spec.mask == "dir_blur"


def test_teaser_rejects_empty_video() -> None:
    with pytest.raises(ValueError, match="positive"):
        build_teaser_spec(_video(0.0), TeaserConfig())


def test_teaser_rejects_zero_tail_fraction_in_config() -> None:
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        TeaserConfig(tail_fraction=0.0)


def test_teaser_uses_hook_clip_payoff_duration_slice() -> None:
    hook = ClipInput(
        id="hook",
        path=Path("assets/hook.mp4"),
        order=0,
        role="hook",
        crop_start_s=1.0,
        crop_end_s=4.0,
    )
    hook_media = MediaInfo(
        path=hook.path,
        duration_s=10.0,
        has_video=True,
    )
    spec = build_teaser_spec(
        _video(30.0),
        TeaserConfig(duration_s=2.5),
        hook_clip=hook,
        hook_media=hook_media,
    )
    assert spec.src_start_s == pytest.approx(1.5)
    assert spec.src_end_s == pytest.approx(4.0)
    assert spec.source_id == "hook"
    assert spec.source_path == hook.path


def test_split_hook_crop_by_duration_head_and_tail() -> None:
    from viral_editor.video.teaser import split_hook_crop_by_duration

    head, tail = split_hook_crop_by_duration(1.0, 4.0, 1.0)
    assert tail == pytest.approx((3.0, 4.0))
    assert head == pytest.approx((1.0, 3.0))


def test_body_output_duration_after_teaser() -> None:
    from viral_editor.models import TeaserSpec

    teaser = TeaserSpec(
        src_start_s=28.5,
        src_end_s=30.0,
        out_duration_s=2.5,
        mask="vignette",
    )
    assert teaser_body_output_duration(13.5, teaser) == pytest.approx(11.0)
    assert teaser_body_output_duration(2.0, teaser) == pytest.approx(0.0)
