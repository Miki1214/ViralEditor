"""Spatial FX planner — zoom punches and rotation shakes from transients."""

from __future__ import annotations

import random
from collections import defaultdict

from viral_editor.models import AudioTimeline, FxEvent, MediaInfo, Transient

ZOOM_MIN = 1.05
ZOOM_MAX = 1.08
ROTATE_MAX_DEG = 1.5
DECAY_MIN_FRAMES = 2
DECAY_MAX_FRAMES = 8
DECAY_BASE_FRAMES = 4
DEFAULT_MAX_EVENTS_PER_SECOND = 8.0
DEFAULT_MERGE_WINDOW_S = 0.05


def _zoom_magnitude(amplitude: float) -> float:
    amp = max(0.0, min(1.0, amplitude))
    return ZOOM_MIN + amp * (ZOOM_MAX - ZOOM_MIN)


def _rotate_magnitude(amplitude: float) -> float:
    amp = max(0.0, min(1.0, amplitude))
    return max(0.1, amp * ROTATE_MAX_DEG)


def _decay_frames(amplitude: float) -> int:
    amp = max(0.0, min(1.0, amplitude))
    scaled = round(DECAY_BASE_FRAMES * (0.5 + amp))
    return max(DECAY_MIN_FRAMES, min(DECAY_MAX_FRAMES, scaled))


def _transient_events(transient: Transient) -> list[FxEvent]:
    timestamp_s = round(transient.timestamp_ms / 1000.0, 6)
    amp = transient.amplitude_normalized
    decay = _decay_frames(amp)

    if transient.type == "drop":
        return [
            FxEvent(
                timestamp_s=timestamp_s,
                kind="zoom",
                magnitude=round(_zoom_magnitude(amp), 4),
                decay_frames=decay,
            )
        ]
    if transient.type == "bass":
        return [
            FxEvent(
                timestamp_s=timestamp_s,
                kind="rotate",
                magnitude=round(_rotate_magnitude(amp), 4),
                decay_frames=decay,
            )
        ]
    return []


def _merge_nearby(events: list[FxEvent], merge_window_s: float) -> list[FxEvent]:
    if not events:
        return []
    ordered = sorted(events, key=lambda event: (event.timestamp_s, event.kind))
    merged: list[FxEvent] = [ordered[0]]
    for event in ordered[1:]:
        prev = merged[-1]
        if (
            event.kind == prev.kind
            and event.timestamp_s - prev.timestamp_s <= merge_window_s
        ):
            if event.magnitude >= prev.magnitude:
                merged[-1] = event
            continue
        merged.append(event)
    return merged


def _cap_events_per_second(
    events: list[FxEvent],
    *,
    max_events_per_second: float,
) -> list[FxEvent]:
    if max_events_per_second <= 0 or not events:
        return events

    per_bucket: dict[int, list[FxEvent]] = defaultdict(list)
    for event in events:
        bucket = int(event.timestamp_s)
        per_bucket[bucket].append(event)

    capped: list[FxEvent] = []
    limit = max(1, int(max_events_per_second))
    for bucket in sorted(per_bucket):
        bucket_events = sorted(
            per_bucket[bucket],
            key=lambda event: event.magnitude,
            reverse=True,
        )
        capped.extend(bucket_events[:limit])
    return sorted(capped, key=lambda event: (event.timestamp_s, event.kind))


def plan_spatial_fx(
    timeline: AudioTimeline,
    media: MediaInfo,
    *,
    seed: int,
    max_events_per_second: float = DEFAULT_MAX_EVENTS_PER_SECOND,
    merge_window_s: float = DEFAULT_MERGE_WINDOW_S,
) -> list[FxEvent]:
    """Map classified transients to zoom/rotate impulses on the output clock.

    Transient timestamps are already on the music/output timeline (seconds from
    the start of the selected music window). Music plays from ``t=0``, so FX at
    ``timestamp_s`` align with the continuous audio track — including during the
    prepended teaser window.
    """
    del media  # reserved for future fps snapping
    events: list[FxEvent] = []
    for transient in timeline.transients:
        events.extend(_transient_events(transient))

    events = _merge_nearby(events, merge_window_s)
    events = _cap_events_per_second(events, max_events_per_second=max_events_per_second)
    return events


def rotate_direction(event: FxEvent, *, seed: int) -> int:
    """Deterministic rotation sign for Phase 6 (+1 or -1)."""
    token = f"{seed}:{event.timestamp_s:.6f}:{event.kind}".encode()
    return -1 if hash(token) % 2 else 1
