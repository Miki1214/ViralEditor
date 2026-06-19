"""Media validation and ffprobe-based ingestion."""

from __future__ import annotations

from pathlib import Path

from pydantic import Field

from viral_editor.config import JobConfig
from viral_editor.models import DomainModel, MediaInfo
from viral_editor.utils.ffmpeg import FFmpegError, run_ffprobe_json
from viral_editor.utils.logging import get_logger
from viral_editor.video.clip_reel import normalize_crop_range

logger = get_logger(__name__)

_VIDEO_DURATION_WARN_RATIO = 0.5


class IngestError(RuntimeError):
    """Raised when job media validation or probing fails."""


class IngestResult(DomainModel):
    """Probed media metadata for both input streams."""

    video: MediaInfo
    audio: MediaInfo
    output_duration_s: float
    clip_media: dict[str, MediaInfo] = Field(default_factory=dict)


def parse_frame_rate(raw: str) -> tuple[float, str]:
    """Parse ffprobe frame rate (e.g. ``30000/1001``) to float seconds."""
    if "/" in raw:
        num_str, den_str = raw.split("/", 1)
        denominator = float(den_str)
        if denominator == 0:
            raise ValueError(f"Invalid frame rate denominator in {raw!r}")
        return float(num_str) / denominator, raw
    return float(raw), raw


def _parse_duration(value: str | None) -> float | None:
    if value is None:
        return None
    duration = float(value)
    return duration if duration >= 0 else None


def _pick_stream(streams: list[dict], codec_type: str) -> dict | None:
    for stream in streams:
        if stream.get("codec_type") == codec_type:
            return stream
    return None


def _duration_from_probe(payload: dict, stream: dict | None) -> float:
    format_info = payload.get("format") or {}
    duration = _parse_duration(format_info.get("duration"))
    if duration is not None:
        return duration

    if stream is not None:
        stream_duration = _parse_duration(stream.get("duration"))
        if stream_duration is not None:
            return stream_duration

    raise IngestError("Could not determine media duration from ffprobe output")


def _log_vfr_warning(path: Path, stream: dict) -> None:
    r_frame_rate = stream.get("r_frame_rate")
    avg_frame_rate = stream.get("avg_frame_rate")
    if not r_frame_rate or not avg_frame_rate or avg_frame_rate in {"0/0", "N/A"}:
        return
    try:
        r_fps, _ = parse_frame_rate(r_frame_rate)
        avg_fps, _ = parse_frame_rate(avg_frame_rate)
    except ValueError:
        return
    if avg_fps <= 0:
        return
    if abs(r_fps - avg_fps) / avg_fps > 0.01:
        logger.warning(
            "Variable frame rate detected in %s (r_frame_rate=%s, avg_frame_rate=%s); "
            "output will be normalized to CFR during encode.",
            path,
            r_frame_rate,
            avg_frame_rate,
        )


def probe_media(path: Path) -> MediaInfo:
    """Probe a media file with ffprobe and return structured metadata."""
    resolved = path.resolve()
    if not resolved.is_file():
        raise IngestError(f"Media file not found: {resolved}")
    if resolved.stat().st_size == 0:
        raise IngestError(f"Media file is empty: {resolved}")

    try:
        payload = run_ffprobe_json(
            ["-show_streams", "-show_format", str(resolved)]
        )
    except FFmpegError as exc:
        raise IngestError(
            f"ffprobe failed for {resolved}. "
            "Ensure the file is a valid media container or try remuxing with: "
            f'ffmpeg -i "{resolved}" -c copy fixed{resolved.suffix}'
        ) from exc

    streams = payload.get("streams") or []
    if not isinstance(streams, list):
        raise IngestError(f"Unexpected ffprobe streams payload for {resolved}")

    video_stream = _pick_stream(streams, "video")
    audio_stream = _pick_stream(streams, "audio")
    primary_stream = video_stream or audio_stream
    duration_s = _duration_from_probe(payload, primary_stream)

    info = MediaInfo(
        path=resolved,
        duration_s=duration_s,
        has_video=video_stream is not None,
        has_audio=audio_stream is not None,
    )

    if video_stream is not None:
        _log_vfr_warning(resolved, video_stream)
        r_frame_rate = video_stream.get("r_frame_rate")
        fps = None
        r_frame_rate_raw = None
        if isinstance(r_frame_rate, str) and r_frame_rate not in {"", "0/0"}:
            try:
                fps, r_frame_rate_raw = parse_frame_rate(r_frame_rate)
            except ValueError:
                logger.warning("Could not parse r_frame_rate %r for %s", r_frame_rate, resolved)

        width = video_stream.get("width")
        height = video_stream.get("height")
        info = info.model_copy(
            update={
                "width": int(width) if width is not None else None,
                "height": int(height) if height is not None else None,
                "fps": fps,
                "r_frame_rate_raw": r_frame_rate_raw,
                "codec_name": video_stream.get("codec_name"),
            }
        )

    if audio_stream is not None:
        sample_rate = audio_stream.get("sample_rate")
        channels = audio_stream.get("channels")
        update: dict = {
            "codec_name": audio_stream.get("codec_name") or info.codec_name,
        }
        if sample_rate is not None:
            update["sample_rate"] = int(sample_rate)
        if channels is not None:
            update["channels"] = int(channels)
        info = info.model_copy(update=update)

    return info


def _ensure_output_writable(output_path: Path) -> None:
    parent = output_path.parent
    if parent.exists() and not parent.is_dir():
        raise IngestError(f"Output parent path is not a directory: {parent}")
    try:
        parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise IngestError(f"Cannot create output directory {parent}: {exc}") from exc
    if not parent.exists():
        raise IngestError(f"Output directory does not exist: {parent}")

    probe = parent / ".write_probe"
    try:
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise IngestError(f"Output directory is not writable: {parent}") from exc


def validate_job(cfg: JobConfig) -> IngestResult:
    """Validate input files, probe media, and derive the output timeline."""
    if not cfg.audio_path.is_file():
        raise IngestError(f"audio_path does not exist: {cfg.audio_path}")
    if cfg.audio_path.stat().st_size == 0:
        raise IngestError(f"audio_path is empty: {cfg.audio_path}")

    if cfg.video_path is not None:
        if not cfg.video_path.is_file():
            raise IngestError(f"video_path does not exist: {cfg.video_path}")
        if cfg.video_path.stat().st_size == 0:
            raise IngestError(f"video_path is empty: {cfg.video_path}")

    _ensure_output_writable(cfg.output_path)

    clip_media: dict[str, MediaInfo] = {}
    for clip in cfg.effective_clips():
        if not clip.path.is_file():
            raise IngestError(f"clip {clip.id} does not exist: {clip.path}")
        if clip.path.stat().st_size == 0:
            raise IngestError(f"clip {clip.id} is empty: {clip.path}")
        info = probe_media(clip.path)
        if not info.has_video:
            raise IngestError(f"No video stream found in clip {clip.id}: {clip.path}")
        start = clip.crop_start_s if clip.crop_start_s is not None else 0.0
        end = clip.crop_end_s if clip.crop_end_s is not None else info.duration_s
        if end <= start:
            raise IngestError(
                f"clip {clip.id} crop_end_s must be greater than crop_start_s"
            )
        norm_start, norm_end = normalize_crop_range(clip, info)
        if (
            abs(norm_start - start) > 1e-6
            or abs(norm_end - end) > 1e-6
            or start < 0
            or end > info.duration_s + 1e-6
        ):
            logger.warning(
                "clip %s crop [%.3f, %.3f] clamped to source duration %.3fs → [%.3f, %.3f]",
                clip.id,
                start,
                end,
                info.duration_s,
                norm_start,
                norm_end,
            )
        clip_media[clip.id] = info

    audio = probe_media(cfg.audio_path)
    if not audio.has_audio:
        raise IngestError(f"No audio stream found in {cfg.audio_path}")

    output_duration_s = audio.duration_s
    effective = cfg.effective_clips()

    if not effective:
        logger.info(
            "Ingest complete — audio-only draft, output duration %.2fs",
            output_duration_s,
        )
        return IngestResult(
            video=MediaInfo(
                path=cfg.audio_path,
                duration_s=0.0,
                has_video=False,
            ),
            audio=audio,
            output_duration_s=output_duration_s,
            clip_media=clip_media,
        )

    video = clip_media[effective[0].id]
    reel_duration = sum(
        (clip_media[c.id].duration_s if c.crop_end_s is None else c.crop_end_s)
        - (c.crop_start_s or 0.0)
        for c in effective
        if c.role == "clip"
    )

    if reel_duration < output_duration_s * _VIDEO_DURATION_WARN_RATIO:
        logger.warning(
            "Source reel (%.2fs from %d clips) is much shorter than the music track (%.2fs); "
            "filler/hook clips will extend the reel during planning.",
            reel_duration,
            len(effective),
            output_duration_s,
        )

    logger.info(
        "Ingest complete — output duration %.2fs (from audio track), %d clips",
        output_duration_s,
        len(effective),
    )
    logger.debug(
        "Primary video: %dx%d @ %.3ffps, %.2fs | Audio: %dHz, %.2fs",
        video.width or 0,
        video.height or 0,
        video.fps or 0.0,
        video.duration_s,
        audio.sample_rate or 0,
        audio.duration_s,
    )

    return IngestResult(
        video=video,
        audio=audio,
        output_duration_s=output_duration_s,
        clip_media=clip_media,
    )
