"""Spatial FX planner — zoom punches and rotation shakes from retention policy."""

from __future__ import annotations

import random
from collections import defaultdict

import numpy as np

from viral_editor.config import RetentionConfig, SpatialFxConfig
from viral_editor.editing.retention_policy import (
    PAN_MAGNITUDE_MAX,
    PAN_MAGNITUDE_MIN,
    place_interrupts,
)
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
    """Legacy fallback when scope lanes are unavailable."""
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
                reason=f"Onset drop @ {timestamp_s:.2f}s",
            )
        ]
    if transient.type == "bass":
        return [
            FxEvent(
                timestamp_s=timestamp_s,
                kind="rotate",
                magnitude=round(_rotate_magnitude(amp), 4),
                decay_frames=decay,
                reason=f"Bass hit @ {timestamp_s:.2f}s",
            )
        ]
    return []


DEFAULT_FPS = 30.0


def _interrupt_to_fx_event(interrupt, *, pan_min_decay_s: float = 0.2) -> FxEvent:
    if interrupt.kind == "zoom":
        amp = (interrupt.magnitude - ZOOM_MIN) / max(ZOOM_MAX - ZOOM_MIN, 1e-9)
        magnitude = round(_zoom_magnitude(amp), 4)
        decay_frames = _decay_frames(amp)
    elif interrupt.kind == "translate":
        amp = (interrupt.magnitude - PAN_MAGNITUDE_MIN) / max(
            PAN_MAGNITUDE_MAX - PAN_MAGNITUDE_MIN,
            1e-9,
        )
        magnitude = round(
            PAN_MAGNITUDE_MIN + amp * (PAN_MAGNITUDE_MAX - PAN_MAGNITUDE_MIN),
            4,
        )
        decay_frames = max(
            _decay_frames(amp),
            round(pan_min_decay_s * DEFAULT_FPS),
        )
    else:
        amp = interrupt.magnitude / ROTATE_MAX_DEG
        magnitude = round(_rotate_magnitude(amp), 4)
        decay_frames = _decay_frames(amp)
    return FxEvent(
        timestamp_s=interrupt.timestamp_s,
        kind=interrupt.kind,
        magnitude=magnitude,
        decay_frames=decay_frames,
        direction=interrupt.direction,
        reason=interrupt.reason,
    )


def _merge_key(event: FxEvent) -> tuple[str, int]:
    if event.kind == "translate":
        return (event.kind, event.direction)
    return (event.kind, 0)


def _merge_nearby(events: list[FxEvent], merge_window_s: float) -> list[FxEvent]:
    if not events:
        return []
    ordered = sorted(events, key=lambda event: (event.timestamp_s, event.kind))
    merged: list[FxEvent] = [ordered[0]]
    for event in ordered[1:]:
        prev = merged[-1]
        if (
            _merge_key(event) == _merge_key(prev)
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
    scope_lanes: dict[str, np.ndarray] | None = None,
    downbeats: list[float] | np.ndarray | None = None,
    beats: list[float] | np.ndarray | None = None,
    window_start_s: float = 0.0,
    window_end_s: float | None = None,
    retention: RetentionConfig | None = None,
    spatial_fx: SpatialFxConfig | None = None,
    translate_enabled: bool | None = None,
) -> list[FxEvent]:
    """Map retention-policy interrupts to zoom/rotate/pan impulses on the output clock."""
    del media, seed  # reserved for future fps snapping / rotate sign
    end_s = window_end_s if window_end_s is not None else timeline.audio_duration_seconds
    cfg = retention or RetentionConfig()
    fx_cfg = spatial_fx or SpatialFxConfig()
    pan_enabled = fx_cfg.translate_enabled if translate_enabled is None else translate_enabled

    if scope_lanes and downbeats is not None:
        interrupts = place_interrupts(
            scope_lanes,
            downbeats,
            window_start_s=window_start_s,
            window_end_s=end_s,
            beats=beats,
            min_gap_s=cfg.interrupt_min_gap_s,
            max_gap_s=cfg.interrupt_max_gap_s,
            translate_enabled=pan_enabled,
            pan_beat_mode=fx_cfg.pan_beat_mode,
            pan_energy_threshold=fx_cfg.pan_energy_threshold,
            pan_energy_floor=fx_cfg.pan_energy_floor,
            pan_hook_by_s=fx_cfg.pan_hook_by_s,
        )
        events = [
            _interrupt_to_fx_event(item, pan_min_decay_s=fx_cfg.pan_min_decay_s)
            for item in interrupts
        ]
    else:
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
