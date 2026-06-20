"""Hook crop / timestretch contract tests — UI label vs segments vs render."""

from __future__ import annotations

from pathlib import Path

import pytest

from viral_editor.api.storyboard import (
    assign_slot_clip,
    hook_output_budget_s,
    hook_unified_crop_range,
    storyboard_segments_debug_payload,
    update_slot_crop,
)
from viral_editor.audio.storyboard import (
    apply_hook_inversion_layout,
    plan_storyboard,
    storyboard_to_segments,
)
from viral_editor.config import TeaserConfig
from viral_editor.models import MediaInfo, MusicBlock, SpeedSegment, Storyboard, StorySlot
from viral_editor.utils.ffmpeg import ffmpeg_available, run_ffmpeg, run_ffprobe_json
from viral_editor.video.proxy_render import composite_output_duration_s, render_composite
from viral_editor.video.teaser import build_teaser_spec


def _block(duration: float = 12.0) -> MusicBlock:
    return MusicBlock(
        id="block_a",
        start_s=0.0,
        end_s=duration,
        duration_s=duration,
        score=0.9,
        drop_count=1,
        transient_count=1,
        label="Chorus",
        reason="test",
        loop_quality=0.8,
        phrase_bars=8,
    )


def _clip_media(clip_len: float, clip_id: str = "slot_0_clip") -> dict[str, MediaInfo]:
    return {
        clip_id: MediaInfo(
            path=Path(f"{clip_id}.mp4"),
            duration_s=clip_len,
            has_video=True,
            width=320,
            height=240,
        )
    }


def _make_hook_split_storyboard(
    clip_len: float,
    payoff_out: float,
) -> tuple[Storyboard, dict[str, MediaInfo]]:
    """Storyboard with hook_start/hook_end and full-clip unified crop."""
    storyboard = plan_storyboard(_block(), features=None, transients=[])
    hook = storyboard.slots[0].model_copy(
        update={
            "assigned_clip_id": "slot_0_clip",
            "crop_start_s": 0.0,
            "crop_end_s": clip_len,
        }
    )
    storyboard = storyboard.model_copy(update={"slots": [hook, *storyboard.slots[1:]]})
    clip_media = _clip_media(clip_len)
    split = apply_hook_inversion_layout(
        storyboard,
        enabled=True,
        payoff_duration_s=payoff_out,
        clip_media=clip_media,
        reshape_crops=True,
    )
    return split, clip_media


def _assert_hook_speed_contract(
    storyboard: Storyboard,
    clip_media: dict[str, MediaInfo],
    *,
    rel: float = 0.02,
) -> None:
    unified = hook_unified_crop_range(storyboard)
    assert unified is not None
    u0, u1 = unified
    hook_budget = hook_output_budget_s(storyboard)
    assert hook_budget > 0
    expected_speed = (u1 - u0) / hook_budget

    hook_start = next(slot for slot in storyboard.slots if slot.role == "hook_start")
    hook_end = next(slot for slot in storyboard.slots if slot.role == "hook_end")

    assert hook_end.crop_end_s == pytest.approx(hook_start.crop_start_s, abs=0.01)
    build_src = hook_end.crop_end_s - hook_end.crop_start_s
    payoff_src = hook_start.crop_end_s - hook_start.crop_start_s
    assert build_src + payoff_src == pytest.approx(u1 - u0, abs=0.02)
    assert payoff_src / hook_start.target_duration_s == pytest.approx(
        build_src / hook_end.target_duration_s,
        rel=rel,
    )
    assert payoff_src / hook_start.target_duration_s == pytest.approx(expected_speed, rel=rel)

    segments, roles, _ = storyboard_to_segments(storyboard, clip_media)
    for segment, role in zip(segments, roles):
        if role not in ("hook_start", "hook_end"):
            continue
        assert segment.speed_factor == pytest.approx(expected_speed, rel=rel)

    payload = storyboard_segments_debug_payload(storyboard, clip_media)
    assert payload["summary"]["hook_speed_s"] == pytest.approx(expected_speed, rel=rel)
    for row in payload["slots"]:
        if row["role"] not in ("hook_start", "hook_end"):
            continue
        assert row["unified_label_speed"] == pytest.approx(expected_speed, rel=rel)
        assert row["speed_factor"] == pytest.approx(row["unified_label_speed"], rel=rel)


@pytest.mark.parametrize(
    ("clip_len", "payoff_out"),
    [
        (14.0, 2.0),
        (20.12, 2.0),
        (10.0, 1.5),
        (7.0, 1.0),
    ],
)
def test_assign_resplit_satisfies_hook_speed_contract(
    clip_len: float,
    payoff_out: float,
) -> None:
    storyboard, clip_media = _make_hook_split_storyboard(clip_len, payoff_out)
    media = clip_media["slot_0_clip"]
    hook_start = next(slot for slot in storyboard.slots if slot.role == "hook_start")
    updated = assign_slot_clip(
        storyboard,
        hook_start.id,
        clip_id="slot_0_clip",
        filename="clip.mp4",
        crop_start_s=0.0,
        crop_end_s=clip_len,
        media=media,
    )
    _assert_hook_speed_contract(updated, clip_media)


@pytest.mark.parametrize(
    ("clip_len", "payoff_out", "crop_start", "crop_end"),
    [
        (20.0, 2.0, 0.0, 14.0),
        (20.0, 2.0, 2.0, 18.0),
        (14.48, 2.0, 0.0, 14.48),
    ],
)
def test_update_slot_crop_resplit_satisfies_contract(
    clip_len: float,
    payoff_out: float,
    crop_start: float,
    crop_end: float,
) -> None:
    storyboard, clip_media = _make_hook_split_storyboard(clip_len, payoff_out)
    media = clip_media["slot_0_clip"]
    hook_start = next(slot for slot in storyboard.slots if slot.role == "hook_start")
    updated = update_slot_crop(
        storyboard,
        hook_start.id,
        crop_start_s=crop_start,
        crop_end_s=crop_end,
        media=media,
        payoff_duration_s=payoff_out,
    )
    _assert_hook_speed_contract(updated, clip_media)


def test_segment_parity_unified_label_matches_speed_factor() -> None:
    storyboard, clip_media = _make_hook_split_storyboard(14.48, 2.0)
    payload = storyboard_segments_debug_payload(storyboard, clip_media)
    unified = payload["summary"]["unified_crop"]
    assert unified is not None
    u0, u1 = unified
    budget = payload["summary"]["hook_budget_s"]
    expected = (u1 - u0) / budget
    assert payload["summary"]["hook_speed_s"] == pytest.approx(expected, rel=0.02)
    hook_rows = [row for row in payload["slots"] if row["role"] in ("hook_start", "hook_end")]
    assert len(hook_rows) == 2
    speeds = {row["speed_factor"] for row in hook_rows}
    assert len(speeds) == 1
    assert next(iter(speeds)) == pytest.approx(expected, rel=0.02)


def test_teaser_payoff_speed_matches_hook_start_segment() -> None:
    clip_len = 10.0
    payoff_out = 2.0
    storyboard, clip_media = _make_hook_split_storyboard(clip_len, payoff_out)
    hook_start = next(slot for slot in storyboard.slots if slot.role == "hook_start")
    hook_end = next(slot for slot in storyboard.slots if slot.role == "hook_end")
    from viral_editor.models import ClipInput

    hook_clip = ClipInput(
        id="slot_0_clip",
        path=clip_media["slot_0_clip"].path,
        order=0,
        crop_start_s=0.0,
        crop_end_s=clip_len,
    )
    spec = build_teaser_spec(
        clip_media["slot_0_clip"],
        TeaserConfig(duration_s=hook_start.target_duration_s),
        hook_clip=hook_clip,
        hook_media=clip_media["slot_0_clip"],
        hook_build_output_s=hook_end.target_duration_s,
    )
    teaser_speed = (spec.src_end_s - spec.src_start_s) / spec.out_duration_s
    segments, roles, _ = storyboard_to_segments(storyboard, clip_media)
    hook_start_speed = segments[roles.index("hook_start")].speed_factor
    assert teaser_speed == pytest.approx(hook_start_speed, rel=0.02)


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


def _probe_duration_s(path: Path) -> float:
    payload = run_ffprobe_json(["-show_entries", "format=duration", str(path)])
    return float(payload["format"]["duration"])


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_render_truth_hook_segments_match_output_budget(tmp_path: Path) -> None:
    clip_len = 10.0
    clip_path = tmp_path / "hook.mp4"
    audio_path = tmp_path / "track.m4a"
    out_path = tmp_path / "composite.mp4"
    _generate_test_clip(clip_path, clip_len)
    _generate_test_audio(audio_path, 8.0)

    media = MediaInfo(
        path=clip_path,
        duration_s=clip_len,
        has_video=True,
        width=320,
        height=240,
    )
    clip_media = {"hook_clip": media}

    hook_start = StorySlot(
        id="slot_0_hook_start",
        order=0,
        label="Hook · start",
        role="hook_start",
        out_start_s=0.0,
        out_end_s=2.0,
        target_duration_s=2.0,
        assigned_clip_id="hook_clip",
        crop_start_s=5.0,
        crop_end_s=10.0,
    )
    hook_end = StorySlot(
        id="slot_0_hook_end",
        order=1,
        label="Hook · end",
        role="hook_end",
        out_start_s=2.0,
        out_end_s=4.0,
        target_duration_s=2.0,
        assigned_clip_id="hook_clip",
        crop_start_s=0.0,
        crop_end_s=5.0,
    )
    storyboard = Storyboard(
        music_block_id="block_a",
        music_start_s=0.0,
        music_end_s=8.0,
        total_duration_s=4.0,
        slots=[hook_start, hook_end],
    )

    segments, roles, _ = storyboard_to_segments(storyboard, clip_media)
    expected_speed = 2.5
    for segment, role in zip(segments, roles):
        assert role in ("hook_start", "hook_end")
        assert segment.speed_factor == pytest.approx(expected_speed, rel=0.02)

    transitions = ["cut", "cut"]
    render_composite(
        audio_path,
        segments,
        transitions,
        clip_paths={"hook_clip": clip_path},
        clip_durations={"hook_clip": clip_len},
        music_start_s=0.0,
        music_end_s=8.0,
        out_path=out_path,
        temp_dir=tmp_path,
        segment_roles=roles,
    )

    expected_duration = composite_output_duration_s(segments, transitions=transitions)
    probed = _probe_duration_s(out_path)
    assert probed == pytest.approx(expected_duration, abs=0.2)

    hook_budget = hook_start.target_duration_s + hook_end.target_duration_s
    unified = hook_unified_crop_range(storyboard)
    assert unified is not None
    label_speed = (unified[1] - unified[0]) / hook_budget
    assert label_speed == pytest.approx(expected_speed, rel=0.02)
    implied_output = (clip_len) / label_speed
    assert implied_output == pytest.approx(hook_budget, rel=0.05)


@pytest.mark.skipif(not ffmpeg_available(), reason="ffmpeg not available")
def test_render_truth_single_segment_duration(tmp_path: Path) -> None:
    """One timestretched segment: 6s source -> 2s output at 3x."""
    clip_path = tmp_path / "clip.mp4"
    audio_path = tmp_path / "track.m4a"
    out_path = tmp_path / "single.mp4"
    _generate_test_clip(clip_path, 10.0)
    _generate_test_audio(audio_path, 4.0)

    segments = [
        SpeedSegment(
            out_start_s=0.0,
            out_end_s=2.0,
            src_start_s=0.0,
            src_end_s=6.0,
            speed_factor=3.0,
            source_id="clip_a",
        )
    ]
    render_composite(
        audio_path,
        segments,
        ["cut"],
        clip_paths={"clip_a": clip_path},
        clip_durations={"clip_a": 10.0},
        music_start_s=0.0,
        music_end_s=4.0,
        out_path=out_path,
        temp_dir=tmp_path,
        segment_roles=["hook_end"],
    )
    probed = _probe_duration_s(out_path)
    assert probed == pytest.approx(2.0, abs=0.15)


def test_update_slot_crop_shrinks_hook_unified_span() -> None:
    """Dragging the hook crop shorter must persist and resplit start/end slots."""
    clip_len = 20.12
    storyboard, clip_media = _make_hook_split_storyboard(clip_len, 2.0)
    media = clip_media["slot_0_clip"]
    hook_start = next(slot for slot in storyboard.slots if slot.role == "hook_start")
    updated = update_slot_crop(
        storyboard,
        hook_start.id,
        crop_start_s=0.0,
        crop_end_s=15.0,
        media=media,
        payoff_duration_s=2.0,
    )
    unified = hook_unified_crop_range(updated)
    assert unified is not None
    assert unified[0] == pytest.approx(0.0)
    assert unified[1] == pytest.approx(15.0, abs=0.02)
    _assert_hook_speed_contract(updated, clip_media)


def test_clip_slot_segment_uses_own_crop_not_hook_unified() -> None:
    """Body clip slots must keep their own crop/speed when hook inversion is enabled."""
    clip_len = 14.48
    storyboard, clip_media = _make_hook_split_storyboard(clip_len, 2.0)
    hook_start = next(slot for slot in storyboard.slots if slot.role == "hook_start")
    hook_end = next(slot for slot in storyboard.slots if slot.role == "hook_end")
    clip_slot = StorySlot(
        id="slot_1",
        order=1,
        label="Clip 1",
        role="clip",
        out_start_s=4.0,
        out_end_s=7.99,
        target_duration_s=3.99,
        transition_in="xfade",
        assigned_clip_id="clip_b",
        crop_start_s=0.0,
        crop_end_s=3.99,
        clip_filename="MVI.mp4",
    )
    clip_media["clip_b"] = MediaInfo(
        path=Path("MVI.mp4"),
        duration_s=clip_len,
        has_video=True,
    )
    slots = sorted(storyboard.slots, key=lambda slot: slot.order)
    slots.insert(1, clip_slot)
    for index, slot in enumerate(slots):
        slots[index] = slot.model_copy(update={"order": index})
    merged = storyboard.model_copy(update={"slots": slots})

    unified = hook_unified_crop_range(merged)
    assert unified is not None
    assert unified[1] - unified[0] == pytest.approx(clip_len, abs=0.02)

    payload = storyboard_segments_debug_payload(merged, clip_media)
    clip_row = next(row for row in payload["slots"] if row["role"] == "clip")
    assert clip_row["src_span_s"] == pytest.approx(3.99, abs=0.01)
    assert clip_row["speed_factor"] == pytest.approx(1.0, abs=0.02)
    assert clip_row["unified_label_speed"] == pytest.approx(1.0, abs=0.02)
    assert clip_row["src_span_s"] != pytest.approx(unified[1] - unified[0], abs=0.5)

    hook_rows = [row for row in payload["slots"] if row["role"] in ("hook_start", "hook_end")]
    hook_speed = payload["summary"]["hook_speed_s"]
    assert hook_speed == pytest.approx(clip_len / hook_output_budget_s(merged), rel=0.02)
    for row in hook_rows:
        assert row["speed_factor"] == pytest.approx(hook_speed, rel=0.02)
        assert row["speed_factor"] != pytest.approx(clip_row["speed_factor"], abs=0.1)

    segments, roles, _ = storyboard_to_segments(merged, clip_media)
    clip_index = roles.index("clip")
    assert segments[clip_index].src_end_s - segments[clip_index].src_start_s == pytest.approx(
        3.99,
        abs=0.01,
    )
    assert segments[clip_index].speed_factor == pytest.approx(1.0, abs=0.02)
    assert hook_start.crop_end_s - hook_start.crop_start_s == pytest.approx(
        clip_len / 2,
        rel=0.05,
    )
    assert hook_end.crop_end_s - hook_end.crop_start_s == pytest.approx(
        clip_len / 2,
        rel=0.05,
    )
