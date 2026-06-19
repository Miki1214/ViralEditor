"""Tests for media probing and job ingestion."""

from __future__ import annotations

from pathlib import Path

import pytest

from viral_editor.config import JobConfig
from viral_editor.ingest.loader import IngestError, probe_media, validate_job


VIDEO_PROBE = {
    "format": {"duration": "30.000000"},
    "streams": [
        {
            "codec_type": "video",
            "codec_name": "h264",
            "width": 1920,
            "height": 1080,
            "r_frame_rate": "30000/1001",
            "avg_frame_rate": "30000/1001",
            "duration": "30.000000",
        }
    ],
}

AUDIO_PROBE = {
    "format": {"duration": "32.410000"},
    "streams": [
        {
            "codec_type": "audio",
            "codec_name": "mp3",
            "sample_rate": "44100",
            "channels": 2,
            "duration": "32.410000",
        }
    ],
}


def _write_minimal_job(tmp_path: Path) -> JobConfig:
    video = tmp_path / "video.mp4"
    audio = tmp_path / "track.mp3"
    output = tmp_path / "output" / "result.mp4"
    video.write_bytes(b"fake-video")
    audio.write_bytes(b"fake-audio")

    cfg = JobConfig(
        video_path=video,
        audio_path=audio,
        output_path=output,
        hook={"text": "Test hook"},
    )
    return cfg


def test_probe_media_parses_video_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "clip.mp4"
    media.write_bytes(b"x")

    monkeypatch.setattr(
        "viral_editor.ingest.loader.run_ffprobe_json",
        lambda _args: VIDEO_PROBE,
    )

    info = probe_media(media)

    assert info.has_video is True
    assert info.has_audio is False
    assert info.duration_s == pytest.approx(30.0)
    assert info.width == 1920
    assert info.height == 1080
    assert info.fps == pytest.approx(30000 / 1001, rel=1e-4)
    assert info.r_frame_rate_raw == "30000/1001"
    assert info.codec_name == "h264"


def test_probe_media_parses_audio_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    media = tmp_path / "track.mp3"
    media.write_bytes(b"x")

    monkeypatch.setattr(
        "viral_editor.ingest.loader.run_ffprobe_json",
        lambda _args: AUDIO_PROBE,
    )

    info = probe_media(media)

    assert info.has_audio is True
    assert info.has_video is False
    assert info.duration_s == pytest.approx(32.41)
    assert info.sample_rate == 44100
    assert info.channels == 2
    assert info.codec_name == "mp3"


def test_probe_media_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(IngestError, match="not found"):
        probe_media(tmp_path / "missing.mp4")


def test_probe_media_empty_file_raises(tmp_path: Path) -> None:
    empty = tmp_path / "empty.mp4"
    empty.write_bytes(b"")

    with pytest.raises(IngestError, match="empty"):
        probe_media(empty)


def test_validate_job_returns_ingest_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _write_minimal_job(tmp_path)

    def fake_probe(path: Path):
        if path.name == "video.mp4":
            return probe_media_from_payload(path, VIDEO_PROBE, video=True)
        return probe_media_from_payload(path, AUDIO_PROBE, video=False)

    monkeypatch.setattr("viral_editor.ingest.loader.probe_media", fake_probe)

    result = validate_job(cfg)

    assert result.output_duration_s == pytest.approx(32.41)
    assert result.video.duration_s == pytest.approx(30.0)
    assert result.audio.duration_s == pytest.approx(32.41)


def test_validate_job_clamps_oversized_crop(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from viral_editor.models import ClipInput

    audio = tmp_path / "track.mp3"
    output = tmp_path / "output" / "result.mp4"
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    audio.write_bytes(b"fake-audio")
    clip_a.write_bytes(b"fake-a")
    clip_b.write_bytes(b"fake-b")

    cfg = JobConfig(
        audio_path=audio,
        output_path=output,
        hook={"text": "Hook"},
        clips=[
            ClipInput(
                id="clip_0",
                path=clip_a,
                order=0,
                role="clip",
                crop_start_s=0.0,
                crop_end_s=40.0,
            ),
            ClipInput(
                id="clip_2",
                path=clip_b,
                order=1,
                role="clip",
                crop_start_s=0.0,
                crop_end_s=25.0,
            ),
        ],
    )

    durations = {
        clip_a.name: 30.0,
        clip_b.name: 20.0,
    }

    def fake_probe(path: Path):
        duration = durations.get(path.name, 30.0)
        if path.suffix == ".mp3":
            return probe_media_from_payload(path, AUDIO_PROBE, video=False)
        payload = {
            **VIDEO_PROBE,
            "format": {"duration": f"{duration:.6f}"},
        }
        return probe_media_from_payload(path, payload, video=True)

    monkeypatch.setattr("viral_editor.ingest.loader.probe_media", fake_probe)

    result = validate_job(cfg)
    assert "clip_0" in result.clip_media
    assert "clip_2" in result.clip_media


def test_validate_job_rejects_missing_video(tmp_path: Path) -> None:
    audio = tmp_path / "track.mp3"
    audio.write_bytes(b"x")
    cfg = JobConfig(
        video_path=tmp_path / "missing.mp4",
        audio_path=audio,
        output_path=tmp_path / "out.mp4",
        hook={"text": "Hook"},
    )

    with pytest.raises(IngestError, match="video_path"):
        validate_job(cfg)


def test_validate_job_rejects_video_without_stream(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _write_minimal_job(tmp_path)

    monkeypatch.setattr(
        "viral_editor.ingest.loader.probe_media",
        lambda path: probe_media_from_payload(
            path,
            {"format": {"duration": "1.0"}, "streams": [{"codec_type": "audio"}]},
            video=False,
        )
        if path.name == "video.mp4"
        else probe_media_from_payload(path, AUDIO_PROBE, video=False),
    )

    with pytest.raises(IngestError, match="No video stream"):
        validate_job(cfg)


def probe_media_from_payload(path: Path, payload: dict, *, video: bool):
    """Build MediaInfo without calling ffprobe (test helper)."""
    from viral_editor.ingest.loader import parse_frame_rate
    from viral_editor.models import MediaInfo

    stream = payload["streams"][0]
    duration_s = float(payload["format"]["duration"])
    if video:
        fps, raw = parse_frame_rate(stream["r_frame_rate"])
        return MediaInfo(
            path=path.resolve(),
            duration_s=duration_s,
            has_video=True,
            width=stream["width"],
            height=stream["height"],
            fps=fps,
            r_frame_rate_raw=raw,
            codec_name=stream["codec_name"],
        )
    return MediaInfo(
        path=path.resolve(),
        duration_s=duration_s,
        has_audio=stream.get("codec_type") == "audio",
        sample_rate=int(stream["sample_rate"]) if "sample_rate" in stream else None,
        channels=stream.get("channels"),
        codec_name=stream.get("codec_name"),
    )
