"""Multi-step auto-rotation detection on clip upload."""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from viral_editor.auto_rotate_settings import AutoRotateSettings
from viral_editor.models import AutoRotationLog, MediaInfo, RotationDirection, RotationVote, write_artifact
from viral_editor.utils.ffmpeg import FFmpegError, run_ffmpeg, run_ffprobe_json
from viral_editor.video.orientation_classifier import (
    class_index_to_degrees,
    class_label,
    predict_orientation,
)

_STEP_PRIORITY: dict[str, int] = {
    "aspect": 0,
    "metadata": 1,
    "orientation": 2,
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
    orientation_vote: RotationVote | None,
) -> tuple[int, str]:
    ordered = [metadata_vote, aspect_vote, orientation_vote]
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

    _metadata, _aspect, _orientation = ordered
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
    """Combine metadata, aspect, and orientation votes into a rotation_deg."""
    metadata_vote = votes[0] if len(votes) > 0 else None
    aspect_vote = votes[1] if len(votes) > 1 else None
    orientation_vote = votes[2] if len(votes) > 2 else None

    rotation_deg, reason = _decide_rotation(metadata_vote, aspect_vote, orientation_vote)
    log = AutoRotationLog(
        metadata_vote=metadata_vote,
        aspect_vote=aspect_vote,
        orientation_vote=orientation_vote,
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
        direction="ccw" if rotate else None,
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


def _vote_from_orientation_class(class_index: int, confidence: float) -> RotationVote:
    suggested_deg = class_index_to_degrees(class_index)
    rotate = suggested_deg != 0
    direction: RotationDirection | None = None
    if suggested_deg == 90:
        direction = "cw"
    elif suggested_deg == 270:
        direction = "ccw"
    return RotationVote(
        step="orientation",
        rotate=rotate,
        direction=direction,
        suggested_deg=suggested_deg,
        confidence=confidence,
        detail=f"orientation classifier: {class_label(class_index)}",
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


def _aggregate_orientation_votes(votes: list[RotationVote]) -> RotationVote | None:
    if not votes:
        return None

    deg_to_class = {0: 0, 90: 1, 180: 2, 270: 3}
    class_indices = [deg_to_class.get(vote.suggested_deg or 0, 0) for vote in votes]
    class_counts = Counter(class_indices)
    winner_class, winner_count = class_counts.most_common(1)[0]
    if winner_count < (len(votes) + 1) // 2:
        return None

    matching = [vote for vote, idx in zip(votes, class_indices) if idx == winner_class]
    avg_conf = sum(vote.confidence or 0.0 for vote in matching) / len(matching)
    return _vote_from_orientation_class(winner_class, avg_conf)


def detect_orientation_rotation(
    path: Path,
    media: MediaInfo,
    *,
    settings: AutoRotateSettings,
    scratch_dir: Path | None = None,
    predict_fn=predict_orientation,
) -> RotationVote | None:
    """Use a dedicated orientation classifier on extracted keyframes."""
    if not settings.enabled or not settings.orientation_enabled:
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

    frame_votes: list[RotationVote] = []
    for frame in frames:
        result = predict_fn(
            frame,
            repo_id=settings.orientation_model_repo,
            model_filename=settings.orientation_model_file,
            min_confidence=settings.min_orientation_confidence,
        )
        if result is None:
            continue
        class_index, confidence = result
        frame_votes.append(_vote_from_orientation_class(class_index, confidence))

    return _aggregate_orientation_votes(frame_votes)


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
) -> int:
    """Run metadata, aspect, and orientation detectors and return rotation_deg."""
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
    orientation_vote = detect_orientation_rotation(
        path,
        media,
        settings=settings,
        scratch_dir=scratch_dir,
    )
    rotation_deg, log = combine_votes([metadata_vote, aspect_vote, orientation_vote])
    log = log.model_copy(
        update={
            "clip_id": clip_id,
            "clip_path": str(path.resolve()),
        }
    )
    write_rotation_log(log, log_dir, clip_id=clip_id)
    return rotation_deg

