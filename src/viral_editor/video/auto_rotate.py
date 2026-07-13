"""Multi-step auto-rotation detection on clip upload."""

from __future__ import annotations

import base64
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import httpx

from viral_editor.auto_rotate_settings import AutoRotateSettings
from viral_editor.models import AutoRotationLog, MediaInfo, RotationDirection, RotationVote, write_artifact
from viral_editor.utils.ffmpeg import FFmpegError, run_ffmpeg, run_ffprobe_json

_STEP_PRIORITY: dict[str, int] = {
    "aspect": 0,
    "metadata": 1,
    "vision": 2,
}


def _rotation_from_vote(vote: RotationVote) -> int:
    if vote.suggested_deg is not None:
        return int(vote.suggested_deg) % 360
    if not vote.rotate:
        return 0
    if vote.direction == "ccw":
        return 270
    return 90


def _votes_agree(left: RotationVote, right: RotationVote) -> bool:
    if left.rotate != right.rotate:
        return False
    if left.suggested_deg is not None and right.suggested_deg is not None:
        return (left.suggested_deg % 360) == (right.suggested_deg % 360)
    if left.direction is not None and right.direction is not None:
        return left.direction == right.direction
    return True


def _merge_votes(*votes: RotationVote) -> RotationVote:
    primary = min(votes, key=lambda vote: _STEP_PRIORITY[vote.step])
    direction: RotationDirection | None = None
    suggested_deg: int | None = None
    for vote in votes:
        if vote.suggested_deg is not None:
            suggested_deg = int(vote.suggested_deg) % 360
            break
        if vote.direction is not None:
            direction = vote.direction
    return RotationVote(
        step=primary.step,
        rotate=primary.rotate,
        direction=direction,
        suggested_deg=suggested_deg,
        detail="merged vote",
    )


def _pick_by_priority(votes: list[RotationVote]) -> RotationVote:
    return min(votes, key=lambda vote: _STEP_PRIORITY[vote.step])


def _decide_rotation(
    metadata_vote: RotationVote | None,
    aspect_vote: RotationVote | None,
    vision_vote: RotationVote | None,
) -> tuple[int, str]:
    ordered = [metadata_vote, aspect_vote, vision_vote]
    active = [vote for vote in ordered if vote is not None]

    if not active:
        return 0, "no recommendation — all steps abstained"

    if len(active) == 1:
        vote = active[0]
        deg = _rotation_from_vote(vote)
        return deg, f"single step ({vote.step}) recommendation"

    if len(active) == 2:
        left, right = active
        if _votes_agree(left, right):
            merged = _merge_votes(left, right)
            return _rotation_from_vote(merged), f"two steps agreed ({left.step}, {right.step})"
        winner = _pick_by_priority([left, right])
        return (
            _rotation_from_vote(winner),
            f"two steps disagreed — priority {winner.step}",
        )

    metadata, aspect, vision = ordered
    agreeing: list[tuple[RotationVote, RotationVote]] = []
    for index, left in enumerate(ordered):
        if left is None:
            continue
        for right in ordered[index + 1 :]:
            if right is None:
                continue
            if _votes_agree(left, right):
                agreeing.append((left, right))

    if not agreeing:
        return 0, "three steps — no two matched"

    first, second = agreeing[0]
    merged = _merge_votes(first, second)
    return _rotation_from_vote(merged), f"at least two steps matched ({first.step}, {second.step})"


def combine_votes(
    votes: list[RotationVote | None],
) -> tuple[int, AutoRotationLog]:
    """Combine metadata, aspect, and vision votes into a rotation_deg."""
    metadata_vote = votes[0] if len(votes) > 0 else None
    aspect_vote = votes[1] if len(votes) > 1 else None
    vision_vote = votes[2] if len(votes) > 2 else None

    rotation_deg, reason = _decide_rotation(metadata_vote, aspect_vote, vision_vote)
    log = AutoRotationLog(
        metadata_vote=metadata_vote,
        aspect_vote=aspect_vote,
        vision_vote=vision_vote,
        final_rotation_deg=rotation_deg,
        reason=reason,
        decided_at=datetime.now(UTC).isoformat(),
    )
    return rotation_deg, log


def detect_aspect_rotation(
    media: MediaInfo,
    *,
    target_aspect: float,
) -> RotationVote:
    """Recommend rotation when stored pixels don't match the target aspect."""
    if not media.width or not media.height:
        return RotationVote(
            step="aspect",
            rotate=False,
            detail="missing width/height",
        )

    source_aspect = media.width / media.height
    rotated_aspect = media.height / media.width
    source_delta = abs(source_aspect - target_aspect)
    rotated_delta = abs(rotated_aspect - target_aspect)

    if source_delta <= rotated_delta and source_aspect < 1.0:
        rotate = False
        detail = "portrait source matches target orientation"
    elif rotated_delta < source_delta or source_aspect >= 1.0:
        rotate = True
        detail = "landscape or square source in portrait job"
    else:
        rotate = False
        detail = "source aspect already closer to target"

    return RotationVote(
        step="aspect",
        rotate=rotate,
        direction=None,
        detail=detail,
    )


def _normalize_metadata_degrees(raw: int) -> int:
    """Map container rotation metadata to a 0/90/180/270 correction."""
    value = int(raw) % 360
    if value < 0:
        value = (360 + value) % 360
    return value


def _vote_from_metadata_degrees(degrees: int, *, detail: str) -> RotationVote:
    normalized = _normalize_metadata_degrees(degrees)
    if normalized == 0:
        return RotationVote(
            step="metadata",
            rotate=False,
            suggested_deg=0,
            detail=detail,
        )
    direction: RotationDirection | None
    if normalized == 90:
        direction = "cw"
    elif normalized == 270:
        direction = "ccw"
    else:
        direction = None
    return RotationVote(
        step="metadata",
        rotate=True,
        direction=direction,
        suggested_deg=normalized,
        detail=detail,
    )


def metadata_vote_from_probe(stream: dict) -> RotationVote | None:
    """Parse rotation metadata from one ffprobe video stream dict."""
    for item in stream.get("side_data_list") or []:
        if not isinstance(item, dict):
            continue
        rotation = item.get("rotation")
        if rotation is not None:
            return _vote_from_metadata_degrees(
                -int(rotation),
                detail=f"side_data rotation={rotation}",
            )

    tags = stream.get("tags") or {}
    rotate_tag = tags.get("rotate")
    if rotate_tag is not None:
        return _vote_from_metadata_degrees(
            int(rotate_tag),
            detail=f"tags.rotate={rotate_tag}",
        )
    return None


def detect_metadata_rotation(path: Path) -> RotationVote | None:
    """Read container rotation metadata via ffprobe."""
    try:
        payload = run_ffprobe_json(
            [
                "-show_streams",
                "-show_entries",
                "stream=side_data_list:stream_tags=rotate",
                str(path.resolve()),
            ]
        )
    except FFmpegError:
        return None

    streams = payload.get("streams") or []
    if not isinstance(streams, list):
        return None
    for stream in streams:
        if not isinstance(stream, dict):
            continue
        if stream.get("codec_type") != "video":
            continue
        vote = metadata_vote_from_probe(stream)
        if vote is not None:
            return vote
    return None


class _HttpClient(Protocol):
    def post(self, url: str, *, json: dict[str, Any], timeout: float) -> Any: ...


_VISION_JSON_RE = re.compile(r"\{[^{}]*\}", re.DOTALL)


def parse_vision_response(
    raw: str,
    *,
    min_confidence: float,
) -> RotationVote | None:
    """Parse one Ollama vision model response into a rotation vote."""
    match = _VISION_JSON_RE.search(raw)
    if match is None:
        return None
    try:
        payload = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None

    confidence = float(payload.get("confidence", 0.0))
    if confidence < min_confidence:
        return None

    rotate = bool(payload.get("rotate"))
    if not rotate:
        return RotationVote(
            step="vision",
            rotate=False,
            confidence=confidence,
            detail="vision model: no rotation needed",
        )

    direction_raw = str(payload.get("direction", "cw")).lower()
    direction: RotationDirection = "ccw" if direction_raw == "ccw" else "cw"
    return RotationVote(
        step="vision",
        rotate=True,
        direction=direction,
        confidence=confidence,
        detail=f"vision model direction={direction}",
    )


def extract_keyframe_paths(
    path: Path,
    *,
    media: MediaInfo,
    count: int,
    scratch_dir: Path,
) -> list[Path]:
    """Extract evenly spaced JPEG keyframes for vision analysis."""
    if count < 1 or media.duration_s <= 0:
        return []

    scratch_dir.mkdir(parents=True, exist_ok=True)
    frames: list[Path] = []
    if count == 1:
        timestamps = [media.duration_s / 2.0]
    else:
        step = media.duration_s / float(count + 1)
        timestamps = [step * (index + 1) for index in range(count)]

    for index, timestamp_s in enumerate(timestamps):
        out_path = scratch_dir / f"frame_{index:02d}.jpg"
        run_ffmpeg(
            [
                "-y",
                "-ss",
                f"{timestamp_s:.6f}",
                "-i",
                str(path.resolve()),
                "-frames:v",
                "1",
                "-q:v",
                "2",
                str(out_path),
            ]
        )
        if out_path.is_file():
            frames.append(out_path)
    return frames


def _analyze_frame_with_ollama(
    frame_path: Path,
    *,
    settings: AutoRotateSettings,
    http_client: _HttpClient,
) -> RotationVote | None:
    image_b64 = base64.b64encode(frame_path.read_bytes()).decode("ascii")
    prompt = (
        "Analyze this video frame orientation for a portrait 9:16 short-form clip. "
        "Reply with JSON only: "
        '{"rotate": true|false, "direction": "cw"|"ccw"|null, "confidence": 0.0-1.0}. '
        "Set rotate=true only when the frame content appears sideways and needs a 90-degree correction."
    )
    try:
        response = http_client.post(
            f"{settings.ollama_host}/api/generate",
            json={
                "model": settings.ollama_model,
                "prompt": prompt,
                "images": [image_b64],
                "stream": False,
            },
            timeout=settings.vision_timeout_s,
        )
        response.raise_for_status()
        raw = str(response.json().get("response", ""))
    except Exception:
        return None
    return parse_vision_response(raw, min_confidence=settings.min_vision_confidence)


def _aggregate_vision_votes(votes: list[RotationVote]) -> RotationVote | None:
    if not votes:
        return None

    rotate_counts = Counter(bool(vote.rotate) for vote in votes)
    rotate_needed = rotate_counts.most_common(1)[0][0]
    if not rotate_needed:
        avg_conf = sum(vote.confidence or 0.0 for vote in votes) / len(votes)
        return RotationVote(
            step="vision",
            rotate=False,
            confidence=avg_conf,
            detail="vision majority: no rotation",
        )

    directional = [vote for vote in votes if vote.rotate and vote.direction is not None]
    if not directional:
        return None
    direction_counts = Counter(vote.direction for vote in directional)
    direction = direction_counts.most_common(1)[0][0]
    if direction_counts.most_common(1)[0][1] < (len(directional) + 1) // 2:
        return None
    avg_conf = sum(vote.confidence or 0.0 for vote in directional) / len(directional)
    return RotationVote(
        step="vision",
        rotate=True,
        direction=direction,
        confidence=avg_conf,
        detail=f"vision majority direction={direction}",
    )


def detect_vision_rotation(
    path: Path,
    media: MediaInfo,
    *,
    settings: AutoRotateSettings,
    scratch_dir: Path | None = None,
    http_client: _HttpClient | None = None,
) -> RotationVote | None:
    """Use local Ollama vision model keyframes to estimate orientation."""
    if not settings.enabled:
        return None

    work_dir = scratch_dir or path.parent / ".auto_rotate_frames"
    frames = extract_keyframe_paths(
        path,
        media=media,
        count=settings.keyframe_count,
        scratch_dir=work_dir,
    )
    if not frames:
        return None

    client = http_client or httpx.Client()
    frame_votes: list[RotationVote] = []
    try:
        for frame in frames:
            vote = _analyze_frame_with_ollama(
                frame,
                settings=settings,
                http_client=client,
            )
            if vote is not None:
                frame_votes.append(vote)
    finally:
        if http_client is None:
            client.close()

    return _aggregate_vision_votes(frame_votes)


def write_rotation_log(log: AutoRotationLog, log_dir: Path, *, clip_id: str) -> Path:
    """Persist one clip auto-rotation decision log."""
    log_dir.mkdir(parents=True, exist_ok=True)
    return write_artifact(log.model_copy(update={"clip_id": clip_id}), clip_id, log_dir)


def run_auto_rotation(
    path: Path,
    media: MediaInfo,
    *,
    clip_id: str,
    target_aspect: float,
    settings: AutoRotateSettings,
    log_dir: Path,
    scratch_dir: Path | None = None,
    http_client: _HttpClient | None = None,
) -> int:
    """Run metadata, aspect, and vision detectors and return rotation_deg."""
    if not settings.enabled:
        log = AutoRotationLog(
            clip_id=clip_id,
            clip_path=str(path.resolve()),
            final_rotation_deg=0,
            reason="auto-rotation disabled",
            decided_at=datetime.now(UTC).isoformat(),
        )
        write_rotation_log(log, log_dir, clip_id=clip_id)
        return 0

    metadata_vote = detect_metadata_rotation(path)
    aspect_vote = detect_aspect_rotation(media, target_aspect=target_aspect)
    vision_vote = detect_vision_rotation(
        path,
        media,
        settings=settings,
        scratch_dir=scratch_dir,
        http_client=http_client,
    )
    rotation_deg, log = combine_votes([metadata_vote, aspect_vote, vision_vote])
    log = log.model_copy(
        update={
            "clip_id": clip_id,
            "clip_path": str(path.resolve()),
        }
    )
    write_rotation_log(log, log_dir, clip_id=clip_id)
    return rotation_deg

