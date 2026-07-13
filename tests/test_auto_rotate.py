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


def test_combine_votes_single_aspect_rotate_defaults_to_90_cw() -> None:
    aspect_vote = RotationVote(
        step="aspect",
        rotate=True,
        direction=None,
        detail="landscape source in portrait job",
    )

    rotation_deg, log = combine_votes([None, aspect_vote, None])

    assert rotation_deg == 90
    assert log.final_rotation_deg == 90
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
        direction="cw",
        suggested_deg=90,
    )
    aspect_vote = RotationVote(step="aspect", rotate=True, direction=None)

    rotation_deg, log = combine_votes([metadata_vote, aspect_vote, None])

    assert rotation_deg == 90
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
    vision_vote = RotationVote(step="vision", rotate=True, direction="ccw")

    rotation_deg, log = combine_votes([metadata_vote, aspect_vote, vision_vote])

    assert rotation_deg == 0
    assert "no two matched" in log.reason.lower()


def test_combine_votes_three_steps_two_match_uses_direction_from_metadata() -> None:
    metadata_vote = RotationVote(
        step="metadata",
        rotate=True,
        direction="ccw",
        suggested_deg=270,
    )
    aspect_vote = RotationVote(step="aspect", rotate=True, direction=None)
    vision_vote = RotationVote(step="vision", rotate=True, direction="cw")

    rotation_deg, log = combine_votes([metadata_vote, aspect_vote, vision_vote])

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
    assert vote.direction is None


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


def test_parse_vision_response_confident_cw() -> None:
    from viral_editor.video.auto_rotate import parse_vision_response

    vote = parse_vision_response(
        '{"rotate": true, "direction": "cw", "confidence": 0.92}',
        min_confidence=0.55,
    )

    assert vote is not None
    assert vote.step == "vision"
    assert vote.rotate is True
    assert vote.direction == "cw"
    assert vote.confidence == pytest.approx(0.92)


def test_parse_vision_response_low_confidence_abstains() -> None:
    from viral_editor.video.auto_rotate import parse_vision_response

    assert (
        parse_vision_response(
            '{"rotate": true, "direction": "cw", "confidence": 0.2}',
            min_confidence=0.55,
        )
        is None
    )


def test_detect_vision_rotation_timeout_abstains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from viral_editor.auto_rotate_settings import AutoRotateSettings
    from viral_editor.video.auto_rotate import detect_vision_rotation

    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"x")
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"jpeg")
    media = MediaInfo(path=media_path, duration_s=3.0, has_video=True, width=1920, height=1080)
    settings = AutoRotateSettings(vision_timeout_s=0.01, keyframe_count=1)

    monkeypatch.setattr(
        "viral_editor.video.auto_rotate.extract_keyframe_paths",
        lambda *_args, **_kwargs: [frame],
    )

    class _TimeoutClient:
        def post(self, *_args, **_kwargs):
            import time

            time.sleep(0.05)
            raise TimeoutError("vision timeout")

    vote = detect_vision_rotation(
        media_path,
        media,
        settings=settings,
        http_client=_TimeoutClient(),
    )

    assert vote is None


def test_detect_vision_rotation_success_aggregates_majority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from viral_editor.auto_rotate_settings import AutoRotateSettings
    from viral_editor.video.auto_rotate import detect_vision_rotation

    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"x")
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"jpeg")
    media = MediaInfo(path=media_path, duration_s=3.0, has_video=True, width=1920, height=1080)
    settings = AutoRotateSettings(keyframe_count=2, min_vision_confidence=0.5)

    monkeypatch.setattr(
        "viral_editor.video.auto_rotate.extract_keyframe_paths",
        lambda *_args, **_kwargs: [frame, frame],
    )

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "response": '{"rotate": true, "direction": "ccw", "confidence": 0.88}',
            }

    class _FakeClient:
        def post(self, *_args, **_kwargs) -> _FakeResponse:
            return _FakeResponse()

    vote = detect_vision_rotation(
        media_path,
        media,
        settings=settings,
        http_client=_FakeClient(),
    )

    assert vote is not None
    assert vote.rotate is True
    assert vote.direction == "ccw"


def test_detect_vision_rotation_malformed_response_abstains(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from viral_editor.auto_rotate_settings import AutoRotateSettings
    from viral_editor.video.auto_rotate import detect_vision_rotation

    media_path = tmp_path / "clip.mp4"
    media_path.write_bytes(b"x")
    frame = tmp_path / "frame.jpg"
    frame.write_bytes(b"jpeg")
    media = MediaInfo(path=media_path, duration_s=3.0, has_video=True, width=1920, height=1080)
    settings = AutoRotateSettings(keyframe_count=1)

    monkeypatch.setattr(
        "viral_editor.video.auto_rotate.extract_keyframe_paths",
        lambda *_args, **_kwargs: [frame],
    )

    class _FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"response": "not json at all"}

    class _FakeClient:
        def post(self, *_args, **_kwargs) -> _FakeResponse:
            return _FakeResponse()

    vote = detect_vision_rotation(
        media_path,
        media,
        settings=settings,
        http_client=_FakeClient(),
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
        "viral_editor.video.auto_rotate.detect_vision_rotation",
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

    assert rotation_deg == 90
    log_path = log_dir / "clip_a.json"
    assert log_path.is_file()
    log = read_artifact(AutoRotationLog, log_path)
    assert log.clip_id == "clip_a"
    assert log.aspect_vote is not None
    assert log.final_rotation_deg == 90
    assert log.reason


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
        "viral_editor.video.auto_rotate.detect_vision_rotation",
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

    assert rotation_deg == 90
    log_path = log_dir / "clip_a.json"
    assert log_path.is_file()
    log = read_artifact(AutoRotationLog, log_path)
    assert log.clip_id == "clip_a"
    assert log.aspect_vote is not None
    assert log.final_rotation_deg == 90
    assert log.reason

