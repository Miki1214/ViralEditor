"""Tests for multi-step auto-rotation detection."""

from __future__ import annotations

from pathlib import Path

import pytest

from viral_editor.models import MediaInfo, RotationVote
from viral_editor.video.auto_rotate import (
    combine_votes,
    detect_aspect_rotation,
    detect_metadata_rotation,
    metadata_vote_from_probe,
)


def test_combine_votes_zero_non_abstaining_steps_returns_no_rotation() -> None:
    rotation_deg, log = combine_votes([None, None, None])

    assert rotation_deg == 0
    assert log.final_rotation_deg == 0
    assert "no recommendation" in log.reason.lower()


def test_combine_votes_single_aspect_rotate_defaults_to_270_ccw() -> None:
    aspect_vote = RotationVote(
        step="aspect",
        rotate=True,
        direction="ccw",
        detail="landscape source in portrait job",
    )

    rotation_deg, log = combine_votes([None, aspect_vote, None])

    assert rotation_deg == 270
    assert log.final_rotation_deg == 270
    assert "single step" in log.reason.lower()


def test_combine_votes_single_metadata_ccw_returns_270() -> None:
    metadata_vote = RotationVote(
        step="metadata",
        rotate=True,
        direction="ccw",
        suggested_deg=270,
        detail="container rotate tag",
    )

    rotation_deg, _log = combine_votes([metadata_vote, None, None])

    assert rotation_deg == 270


def test_combine_votes_two_steps_agree_metadata_and_aspect() -> None:
    metadata_vote = RotationVote(
        step="metadata",
        rotate=True,
        direction="ccw",
        suggested_deg=270,
    )
    aspect_vote = RotationVote(step="aspect", rotate=True, direction="ccw")

    rotation_deg, log = combine_votes([metadata_vote, aspect_vote, None])

    assert rotation_deg == 270
    assert "agreed" in log.reason.lower()


def test_combine_votes_two_steps_disagree_prefers_aspect() -> None:
    metadata_vote = RotationVote(
        step="metadata",
        rotate=True,
        direction="ccw",
        suggested_deg=270,
    )
    aspect_vote = RotationVote(step="aspect", rotate=False, direction=None)

    rotation_deg, log = combine_votes([metadata_vote, aspect_vote, None])

    assert rotation_deg == 0
    assert "priority aspect" in log.reason.lower()


def test_combine_votes_three_steps_no_two_match_returns_zero() -> None:
    metadata_vote = RotationVote(step="metadata", rotate=True, direction="cw", suggested_deg=90)
    aspect_vote = RotationVote(step="aspect", rotate=False, direction=None)
    orientation_vote = RotationVote(step="orientation", rotate=True, direction="ccw", suggested_deg=270)

    rotation_deg, log = combine_votes([metadata_vote, aspect_vote, orientation_vote])

    assert rotation_deg == 0
    assert "no two matched" in log.reason.lower()


def test_combine_votes_three_steps_two_match_uses_direction_from_metadata() -> None:
    metadata_vote = RotationVote(
        step="metadata",
        rotate=True,
        direction="ccw",
        suggested_deg=270,
    )
    aspect_vote = RotationVote(step="aspect", rotate=True, direction="ccw")
    orientation_vote = RotationVote(
        step="orientation",
        rotate=True,
        direction="cw",
        suggested_deg=90,
    )

    rotation_deg, log = combine_votes([metadata_vote, aspect_vote, orientation_vote])

    assert rotation_deg == 270
    assert "matched" in log.reason.lower()


PORTRAIT_TARGET_ASPECT = 9 / 16


def test_detect_aspect_rotation_landscape_source_in_portrait_job() -> None:
    media = MediaInfo(
        path=Path("clip.mp4"),
        duration_s=5.0,
        has_video=True,
        width=1920,
        height=1080,
    )

    vote = detect_aspect_rotation(media, target_aspect=PORTRAIT_TARGET_ASPECT)

    assert vote.step == "aspect"
    assert vote.rotate is True
    assert vote.direction == "ccw"


def test_detect_aspect_rotation_portrait_source_needs_no_rotation() -> None:
    media = MediaInfo(
        path=Path("clip.mp4"),
        duration_s=5.0,
        has_video=True,
        width=1080,
        height=1920,
    )

    vote = detect_aspect_rotation(media, target_aspect=PORTRAIT_TARGET_ASPECT)

    assert vote.rotate is False


def test_detect_aspect_rotation_square_source_in_portrait_job() -> None:
    media = MediaInfo(
        path=Path("clip.mp4"),
        duration_s=5.0,
        has_video=True,
        width=1080,
        height=1080,
    )

    vote = detect_aspect_rotation(media, target_aspect=PORTRAIT_TARGET_ASPECT)

    assert vote.rotate is True


def test_metadata_vote_from_probe_side_data_rotation_90() -> None:
    stream = {
        "codec_type": "video",
        "side_data_list": [{"side_data_type": "Display Matrix", "rotation": -90}],
    }

    vote = metadata_vote_from_probe(stream)

    assert vote is not None
    assert vote.step == "metadata"
    assert vote.rotate is True
    assert vote.suggested_deg == 90


def test_metadata_vote_from_probe_tags_rotate_270() -> None:
    stream = {
        "codec_type": "video",
        "tags": {"rotate": "270"},
    }

    vote = metadata_vote_from_probe(stream)

    assert vote is not None
    assert vote.rotate is True
    assert vote.suggested_deg == 270
    assert vote.direction == "ccw"


def test_metadata_vote_from_probe_without_rotation_abstains() -> None:
    stream = {"codec_type": "video", "width": 1920, "height": 1080}

    assert metadata_vote_from_probe(stream) is None


def test_detect_metadata_rotation_reads_ffprobe_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "phone.mp4"
    media.write_bytes(b"x")
    probe = {
        "streams": [
            {
                "codec_type": "video",
                "side_data_list": [{"rotation": -90}],
            }
        ]
    }
    monkeypatch.setattr(
        "viral_editor.video.auto_rotate.run_ffprobe_json",
        lambda _args: probe,
    )

    vote = detect_metadata_rotation(media)

    assert vote is not None
    assert vote.suggested_deg == 90


def test_vote_from_orientation_class_maps_correction_degrees() -> None:
    from viral_editor.video.auto_rotate import _vote_from_orientation_class

    upright = _vote_from_orientation_class(0, 0.95)
    assert upright.rotate is False
    assert upright.suggested_deg == 0

    cw = _vote_from_orientation_class(1, 0.91)
    assert cw.rotate is True
    assert cw.suggested_deg == 90
    assert cw.direction == "cw"

    ccw = _vote_from_orientation_class(3, 0.88)
    assert ccw.rotate is True
    assert ccw.suggested_deg == 270
    assert ccw.direction == "ccw"


def test_detect_orientation_rotation_aggregates_majority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from viral_editor.auto_rotate_settings import AutoRotateSettings
    from viral_editor.video.auto_rotate import detect_orientation_rotation

    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"x")
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"jpeg")
    media = MediaInfo(path=media_path, duration_s=3.0, has_video=True, width=1920, height=1080)
    settings = AutoRotateSettings(keyframe_count=2, min_orientation_confidence=0.5)

    monkeypatch.setattr(
        "viral_editor.video.auto_rotate.extract_keyframe_paths",
        lambda *_args, **_kwargs: [frame, frame],
    )

    def fake_predict(_path, **kwargs):
        return 3, 0.9

    vote = detect_orientation_rotation(
        media_path,
        media,
        settings=settings,
        predict_fn=fake_predict,
    )

    assert vote is not None
    assert vote.step == "orientation"
    assert vote.suggested_deg == 270
    assert vote.direction == "ccw"


def test_detect_orientation_rotation_low_confidence_abstains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from viral_editor.auto_rotate_settings import AutoRotateSettings
    from viral_editor.video.auto_rotate import detect_orientation_rotation

    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"x")
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"jpeg")
    media = MediaInfo(path=media_path, duration_s=3.0, has_video=True, width=1920, height=1080)
    settings = AutoRotateSettings(keyframe_count=1, min_orientation_confidence=0.8)

    monkeypatch.setattr(
        "viral_editor.video.auto_rotate.extract_keyframe_paths",
        lambda *_args, **_kwargs: [frame],
    )

    vote = detect_orientation_rotation(
        media_path,
        media,
        settings=settings,
        predict_fn=lambda *_args, **_kwargs: None,
    )

    assert vote is None


def test_run_auto_rotation_writes_log_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from viral_editor.auto_rotate_settings import AutoRotateSettings
    from viral_editor.models import AutoRotationLog, read_artifact
    from viral_editor.video.auto_rotate import run_auto_rotation

    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"x")
    media = MediaInfo(path=media_path, duration_s=2.0, has_video=True, width=1920, height=1080)
    settings = AutoRotateSettings(enabled=True, keyframe_count=0)
    log_dir = tmp_path / "rotation_log"

    monkeypatch.setattr(
        "viral_editor.video.auto_rotate.detect_metadata_rotation",
        lambda _path: None,
    )
    monkeypatch.setattr(
        "viral_editor.video.auto_rotate.detect_orientation_rotation",
        lambda *_args, **_kwargs: None,
    )

    rotation_deg = run_auto_rotation(
        media_path,
        media,
        clip_id="clip_a",
        target_aspect=PORTRAIT_TARGET_ASPECT,
        settings=settings,
        log_dir=log_dir,
    )

    assert rotation_deg == 270
    log_path = log_dir / "clip_a.json"
    assert log_path.is_file()
    log = read_artifact(AutoRotationLog, log_path)
    assert log.clip_id == "clip_a"
    assert log.aspect_vote is not None
    assert log.final_rotation_deg == 270
    assert log.reason

