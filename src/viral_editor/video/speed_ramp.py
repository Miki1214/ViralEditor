"""Dynamic speed-ramp planner — maps music time to source video consumption."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from viral_editor.audio.features import BeatSyncFeatures
from viral_editor.config import SpeedRampConfig
from viral_editor.models import (
    AudioTimeline,
    BudgetPolicy,
    MediaInfo,
    MusicSection,
    SpeedCurvePoint,
    SpeedRampOption,
    SpeedRampOptionSet,
    SpeedRampPlan,
    SpeedSegment,
    Transient,
)
from viral_editor.video.speed_presets import PRESETS, SpeedPreset, resolve_params

DEFAULT_HOP_LENGTH = 512
DEFAULT_SR = 22050
DEFAULT_OUTPUT_FPS = 60.0
DEFAULT_SRC_FPS = 30.0
PERCUSSIVE_WINDOW_S = 0.25
BASS_WINDOW_S = 0.18
CURVE_MAX_POINTS = 120


@dataclass(frozen=True)
class _RawSegment:
    out_start_s: float
    out_end_s: float
    speed_factor: float


def trim_envelope_to_window(
    onset_envelope: np.ndarray,
    *,
    start_s: float,
    end_s: float,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
) -> np.ndarray:
    """Slice an onset envelope to match a trimmed ``AudioTimeline`` window."""
    if onset_envelope.size == 0:
        return onset_envelope
    start_idx = max(0, int(round(start_s * sr / hop_length)))
    end_idx = min(len(onset_envelope), int(round(end_s * sr / hop_length)))
    if end_idx <= start_idx:
        return np.array([], dtype=onset_envelope.dtype)
    return onset_envelope[start_idx:end_idx].copy()


def trim_beat_features_to_window(
    features: BeatSyncFeatures,
    *,
    start_s: float,
    end_s: float,
) -> BeatSyncFeatures:
    """Shift beat-sync features into a trimmed output timeline starting at 0."""
    beat_mask = (features.beat_times_s >= start_s - 1e-6) & (features.beat_times_s <= end_s + 1e-6)
    beat_times = features.beat_times_s[beat_mask] - start_s
    down_mask = (features.downbeat_times_s >= start_s - 1e-6) & (
        features.downbeat_times_s <= end_s + 1e-6
    )
    downbeats = features.downbeat_times_s[down_mask] - start_s

    def _slice(matrix: np.ndarray) -> np.ndarray:
        if matrix.ndim != 2 or matrix.shape[1] == 0:
            return matrix
        indices = np.where(beat_mask)[0]
        if indices.size == 0:
            return matrix[:, :0]
        return matrix[:, indices]

    meta = features.meta.model_copy(
        update={
            "n_beats": int(beat_times.size),
            "n_downbeats": int(downbeats.size),
        }
    )
    return BeatSyncFeatures(
        meta=meta,
        beat_times_s=beat_times.astype(float),
        downbeat_times_s=downbeats.astype(float),
        chroma_sync=_slice(features.chroma_sync),
        mfcc_sync=_slice(features.mfcc_sync),
        rms_sync=_slice(features.rms_sync),
        contrast_sync=_slice(features.contrast_sync),
        tonnetz_sync=_slice(features.tonnetz_sync),
    )


def _mean_envelope(
    onset_envelope: np.ndarray,
    start_s: float,
    end_s: float,
    *,
    hop_length: int,
    sr: int,
) -> float:
    if end_s <= start_s or onset_envelope.size == 0:
        return 0.0
    start_idx = max(0, int(round(start_s * sr / hop_length)))
    end_idx = min(len(onset_envelope), max(start_idx + 1, int(round(end_s * sr / hop_length))))
    if end_idx <= start_idx:
        mid = (start_s + end_s) / 2.0
        index = max(0, min(int(round(mid * sr / hop_length)), len(onset_envelope) - 1))
        peak = float(onset_envelope.max())
        return float(onset_envelope[index] / peak) if peak > 0 else 0.0
    peak = float(onset_envelope.max())
    if peak <= 0:
        return 0.0
    return float(onset_envelope[start_idx:end_idx].mean() / peak)


def _clamp_speed(value: float, preset: SpeedPreset) -> float:
    return max(preset.s_min, min(preset.s_max, value))


def _quantize_speed(value: float, preset: SpeedPreset) -> float:
    quantum = preset.speed_quantum
    if quantum <= 0:
        return _clamp_speed(value, preset)
    return _clamp_speed(round(value / quantum) * quantum, preset)


def _drop_slow_windows(
    transients: list[Transient],
    *,
    output_duration_s: float,
    drop_window_ms: int,
) -> list[tuple[float, float]]:
    half = drop_window_ms / 2000.0
    windows: list[tuple[float, float]] = []
    for transient in transients:
        if transient.type != "drop":
            continue
        center = transient.timestamp_ms / 1000.0
        start = max(0.0, center - half)
        end = min(output_duration_s, center + half)
        if end > start:
            windows.append((start, end))
    return windows


def _bass_windows(
    transients: list[Transient],
    *,
    output_duration_s: float,
) -> list[tuple[float, float]]:
    half = BASS_WINDOW_S / 2.0
    windows: list[tuple[float, float]] = []
    for transient in transients:
        if transient.type != "bass":
            continue
        center = transient.timestamp_ms / 1000.0
        start = max(0.0, center - half)
        end = min(output_duration_s, center + half)
        if end > start:
            windows.append((start, end))
    return windows


def _segment_overlaps(
    out_start_s: float,
    out_end_s: float,
    windows: list[tuple[float, float]],
) -> bool:
    return any(out_start_s < w_end and out_end_s > w_start for w_start, w_end in windows)


def _section_at(time_s: float, sections: list[MusicSection]) -> MusicSection | None:
    for section in sections:
        if section.start_s <= time_s < section.end_s:
            return section
    return None


def _percussive_density(
    transients: list[Transient],
    start_s: float,
    end_s: float,
) -> float:
    count = sum(
        1
        for t in transients
        if t.type == "percussive" and start_s <= t.timestamp_ms / 1000.0 < end_s
    )
    duration = max(end_s - start_s, 1e-6)
    return min(1.0, count / max(1.0, duration / PERCUSSIVE_WINDOW_S))


def _beat_grid_boundaries(
    output_duration_s: float,
    *,
    preset: SpeedPreset,
    features: BeatSyncFeatures | None,
    bpm: float,
    drop_windows: list[tuple[float, float]],
) -> list[float]:
    boundaries = {0.0, output_duration_s}
    if preset.snap_mode == "downbeat" and features is not None and features.downbeat_times_s.size:
        for t in features.downbeat_times_s:
            if 0.0 <= t <= output_duration_s:
                boundaries.add(round(float(t), 6))
    elif preset.snap_mode == "beat" and features is not None and features.beat_times_s.size:
        for t in features.beat_times_s:
            if 0.0 <= t <= output_duration_s:
                boundaries.add(round(float(t), 6))
    else:
        step_s = (
            preset.grid_step_ms / 1000.0
            if preset.grid_step_ms is not None
            else (60.0 / bpm if bpm > 0 else 0.1)
        )
        if step_s > 0:
            t = 0.0
            while t < output_duration_s - 1e-9:
                boundaries.add(round(t, 6))
                t += step_s
    for drop_start, drop_end in drop_windows:
        boundaries.add(round(drop_start, 6))
        boundaries.add(round(drop_end, 6))
    ordered = sorted(boundaries)
    min_len = preset.min_segment_ms / 1000.0
    merged = [ordered[0]]
    for boundary in ordered[1:]:
        if boundary - merged[-1] < min_len:
            continue
        merged.append(boundary)
    if merged[-1] != output_duration_s:
        if output_duration_s - merged[-1] < min_len and len(merged) > 1:
            merged[-1] = output_duration_s
        else:
            merged.append(output_duration_s)
    return merged


def _beat_energy(
    start_s: float,
    end_s: float,
    *,
    features: BeatSyncFeatures | None,
    onset_envelope: np.ndarray,
    hop_length: int,
    sr: int,
) -> float:
    if features is not None and features.rms_sync.size:
        mid = (start_s + end_s) / 2.0
        beat_idx = int(np.argmin(np.abs(features.beat_times_s - mid)))
        beat_idx = max(0, min(beat_idx, features.rms_sync.shape[1] - 1))
        rms_val = float(features.rms_sync[:, beat_idx].mean())
        rms_peak = float(features.rms_sync.max()) if features.rms_sync.size else 1.0
        if rms_peak > 0:
            return min(1.0, rms_val / rms_peak)
    return _mean_envelope(onset_envelope, start_s, end_s, hop_length=hop_length, sr=sr)


def _target_speed(
    start_s: float,
    end_s: float,
    *,
    preset: SpeedPreset,
    energy: float,
    density: float,
    section: MusicSection | None,
    drop_windows: list[tuple[float, float]],
    bass_windows: list[tuple[float, float]],
) -> float:
    if _segment_overlaps(start_s, end_s, drop_windows):
        return preset.s_min

    section_slow = 0.0
    if section is not None:
        section_slow = section.energy * preset.section_bias
        if section.is_repeated:
            section_slow += 0.25 * preset.section_bias

    opening_slow = 0.0
    if preset.opening_slow_s > 0 and end_s <= preset.opening_slow_s:
        opening_slow = preset.section_bias * 0.5

    raw = (
        preset.s_max
        - energy * preset.alpha
        - density * preset.density_gain * preset.s_max * 0.08
        - section_slow * preset.s_max
        - opening_slow * preset.s_max
    )
    speed = _quantize_speed(_clamp_speed(raw, preset), preset)

    if _segment_overlaps(start_s, end_s, bass_windows) and preset.bass_accent > 0:
        dip = preset.bass_accent * (speed - preset.s_min)
        speed = _quantize_speed(max(preset.s_min, speed - dip), preset)
    return speed


def _build_raw_segments(
    boundaries: list[float],
    *,
    preset: SpeedPreset,
    onset_envelope: np.ndarray,
    timeline: AudioTimeline,
    sections: list[MusicSection],
    features: BeatSyncFeatures | None,
    drop_windows: list[tuple[float, float]],
    bass_windows: list[tuple[float, float]],
    hop_length: int,
    sr: int,
) -> list[_RawSegment]:
    segments: list[_RawSegment] = []
    for out_start, out_end in zip(boundaries[:-1], boundaries[1:], strict=False):
        if out_end <= out_start + 1e-9:
            continue
        mid = (out_start + out_end) / 2.0
        energy = _beat_energy(
            out_start,
            out_end,
            features=features,
            onset_envelope=onset_envelope,
            hop_length=hop_length,
            sr=sr,
        )
        density = _percussive_density(timeline.transients, out_start, out_end)
        section = _section_at(mid, sections)
        speed = _target_speed(
            out_start,
            out_end,
            preset=preset,
            energy=energy,
            density=density,
            section=section,
            drop_windows=drop_windows,
            bass_windows=bass_windows,
        )
        segments.append(_RawSegment(out_start, out_end, speed))
    return segments


def _scale_speeds_to_budget(
    raw_segments: list[_RawSegment],
    src_duration_s: float,
    preset: SpeedPreset,
) -> list[_RawSegment]:
    total_src = sum(seg.speed_factor * (seg.out_end_s - seg.out_start_s) for seg in raw_segments)
    if total_src <= 1e-9 or src_duration_s <= 0:
        return raw_segments
    factor = src_duration_s / total_src
    return [
        _RawSegment(
            seg.out_start_s,
            seg.out_end_s,
            _quantize_speed(_clamp_speed(seg.speed_factor * factor, preset), preset),
        )
        for seg in raw_segments
    ]


def cap_output_duration_to_source(
    output_duration_s: float,
    src_duration_s: float,
    *,
    s_min: float,
    budget_policy: BudgetPolicy = "scale",
) -> float:
    """Limit the output timeline to what the source can cover without looping."""
    if budget_policy == "loop" or src_duration_s <= 0 or output_duration_s <= 0:
        return output_duration_s
    max_output = src_duration_s / max(s_min, 1e-6)
    return min(output_duration_s, max_output)


def _materialize_segments(
    raw_segments: list[_RawSegment],
    *,
    src_duration_s: float,
    preset: SpeedPreset,
) -> list[SpeedSegment]:
    segments: list[SpeedSegment] = []
    src_cursor = 0.0
    for raw in raw_segments:
        out_len = raw.out_end_s - raw.out_start_s
        src_len = raw.speed_factor * out_len
        if preset.budget_policy == "loop" and src_duration_s > 0:
            src_start = src_cursor % src_duration_s
        else:
            src_start = src_cursor
        src_end = src_cursor + src_len
        src_cursor += src_len
        segments.append(
            SpeedSegment(
                out_start_s=raw.out_start_s,
                out_end_s=raw.out_end_s,
                src_start_s=src_start,
                src_end_s=src_end,
                speed_factor=raw.speed_factor,
            )
        )
    return segments


def _nudge_last_segment_to_budget(
    segments: list[SpeedSegment],
    src_duration_s: float,
    preset: SpeedPreset,
) -> list[SpeedSegment]:
    if not segments or src_duration_s <= 0 or preset.budget_policy != "scale":
        return segments
    last = segments[-1]
    remainder = src_duration_s - last.src_start_s
    out_len = last.out_end_s - last.out_start_s
    if out_len <= 1e-9:
        return segments
    speed = _clamp_speed(remainder / out_len, preset)
    updated = last.model_copy(
        update={
            "src_end_s": last.src_start_s + speed * out_len,
            "speed_factor": speed,
        }
    )
    return [*segments[:-1], updated]


def _snap_segments_to_frames(
    segments: list[SpeedSegment],
    *,
    output_duration_s: float,
    output_fps: float,
    src_fps: float,
) -> list[SpeedSegment]:
    if not segments:
        return segments
    out_frame_boundaries = [round(seg.out_start_s * output_fps) for seg in segments]
    out_frame_boundaries.append(round(output_duration_s * output_fps))
    snapped: list[SpeedSegment] = []
    src_cursor = 0.0
    for index, seg in enumerate(segments):
        out_start = out_frame_boundaries[index] / output_fps
        out_end = out_frame_boundaries[index + 1] / output_fps
        if out_end <= out_start + 1e-9:
            continue
        out_len = out_end - out_start
        src_len = seg.speed_factor * out_len
        src_start = round(src_cursor * src_fps) / src_fps if src_fps > 0 else src_cursor
        src_end = round((src_cursor + src_len) * src_fps) / src_fps if src_fps > 0 else src_cursor + src_len
        if src_end <= src_start:
            src_end = src_start + (1.0 / src_fps if src_fps > 0 else 0.001)
        snapped.append(
            SpeedSegment(
                out_start_s=round(out_start, 6),
                out_end_s=round(out_end, 6),
                src_start_s=round(src_start, 6),
                src_end_s=round(src_end, 6),
                speed_factor=seg.speed_factor,
            )
        )
        src_cursor += src_len
    return snapped


def _build_speed_curve(
    segments: list[SpeedSegment],
    *,
    preset: SpeedPreset,
    drop_windows: list[tuple[float, float]],
    bass_windows: list[tuple[float, float]],
    output_duration_s: float,
) -> list[SpeedCurvePoint]:
    if not segments or output_duration_s <= 0:
        return []
    if len(segments) <= CURVE_MAX_POINTS:
        indices = range(len(segments))
    else:
        indices = np.linspace(0, len(segments) - 1, CURVE_MAX_POINTS).astype(int)

    slow_threshold = preset.s_min + (preset.s_max - preset.s_min) * 0.08
    points: list[SpeedCurvePoint] = []
    for index in indices:
        seg = segments[int(index)]
        mid = (seg.out_start_s + seg.out_end_s) / 2.0
        points.append(
            SpeedCurvePoint(
                t=round(mid, 4),
                speed=round(seg.speed_factor, 4),
                is_slow_zone=seg.speed_factor <= slow_threshold
                or _segment_overlaps(seg.out_start_s, seg.out_end_s, drop_windows),
                is_bass_accent=_segment_overlaps(seg.out_start_s, seg.out_end_s, bass_windows),
            )
        )
    return points


def _summarize_plan(
    segments: list[SpeedSegment],
    *,
    preset: SpeedPreset,
    drop_windows: list[tuple[float, float]],
    bass_windows: list[tuple[float, float]],
    output_duration_s: float,
) -> tuple[float, float, float, int, list[SpeedCurvePoint]]:
    if not segments:
        return 0.0, 0.0, 0.0, 0, []
    speeds = [seg.speed_factor for seg in segments]
    slow_threshold = preset.s_min + (preset.s_max - preset.s_min) * 0.08
    slow_count = sum(
        1
        for seg in segments
        if seg.speed_factor <= slow_threshold
        or _segment_overlaps(seg.out_start_s, seg.out_end_s, drop_windows)
    )
    curve = _build_speed_curve(
        segments,
        preset=preset,
        drop_windows=drop_windows,
        bass_windows=bass_windows,
        output_duration_s=output_duration_s,
    )
    return (
        float(np.mean(speeds)),
        float(max(speeds)),
        float(min(speeds)),
        slow_count,
        curve,
    )


def _plan_with_preset(
    timeline: AudioTimeline,
    onset_envelope: np.ndarray,
    video: MediaInfo,
    *,
    output_duration_s: float,
    preset: SpeedPreset,
    features: BeatSyncFeatures | None = None,
    sections: list[MusicSection] | None = None,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
    output_fps: float = DEFAULT_OUTPUT_FPS,
) -> SpeedRampPlan:
    sections = sections or []
    if output_duration_s <= 0:
        return SpeedRampPlan(
            style=preset.style,
            output_duration_s=0.0,
            src_duration_s=video.duration_s,
            budget_policy=preset.budget_policy,
            segments=[],
        )

    src_duration_s = video.duration_s
    src_fps = video.fps or DEFAULT_SRC_FPS
    requested_output_s = output_duration_s
    output_duration_s = cap_output_duration_to_source(
        output_duration_s,
        src_duration_s,
        s_min=preset.s_min,
        budget_policy=preset.budget_policy,
    )
    drop_windows = _drop_slow_windows(
        timeline.transients,
        output_duration_s=output_duration_s,
        drop_window_ms=preset.drop_window_ms,
    )
    bass_windows = _bass_windows(timeline.transients, output_duration_s=output_duration_s)
    boundaries = _beat_grid_boundaries(
        output_duration_s,
        preset=preset,
        features=features,
        bpm=timeline.global_bpm,
        drop_windows=drop_windows,
    )
    raw_segments = _build_raw_segments(
        boundaries,
        preset=preset,
        onset_envelope=onset_envelope,
        timeline=timeline,
        sections=sections,
        features=features,
        drop_windows=drop_windows,
        bass_windows=bass_windows,
        hop_length=hop_length,
        sr=sr,
    )
    if not raw_segments:
        raw_segments = [_RawSegment(0.0, output_duration_s, _clamp_speed(preset.s_max, preset))]

    if preset.budget_policy == "scale":
        raw_segments = _scale_speeds_to_budget(raw_segments, src_duration_s, preset)

    segments = _materialize_segments(raw_segments, src_duration_s=src_duration_s, preset=preset)
    segments = _nudge_last_segment_to_budget(segments, src_duration_s, preset)
    segments = _snap_segments_to_frames(
        segments,
        output_duration_s=output_duration_s,
        output_fps=output_fps,
        src_fps=src_fps,
    )
    avg_s, max_s, min_s, slow_count, curve = _summarize_plan(
        segments,
        preset=preset,
        drop_windows=drop_windows,
        bass_windows=bass_windows,
        output_duration_s=output_duration_s,
    )
    return SpeedRampPlan(
        style=preset.style,
        output_duration_s=output_duration_s,
        requested_output_duration_s=(
            requested_output_s
            if requested_output_s > output_duration_s + 1e-6
            else None
        ),
        src_duration_s=src_duration_s,
        budget_policy=preset.budget_policy,
        avg_speed=round(avg_s, 3),
        max_speed=round(max_s, 3),
        min_speed=round(min_s, 3),
        slow_zone_count=slow_count,
        speed_curve=curve,
        segments=segments,
    )


def plan_speed_segments(
    timeline: AudioTimeline,
    onset_envelope: np.ndarray,
    video: MediaInfo,
    *,
    output_duration_s: float,
    config: SpeedRampConfig,
    features: BeatSyncFeatures | None = None,
    sections: list[MusicSection] | None = None,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
    output_fps: float = DEFAULT_OUTPUT_FPS,
) -> SpeedRampPlan:
    """Build a gapless speed plan for the selected config style."""
    preset = resolve_params(config, config.style)
    return _plan_with_preset(
        timeline,
        onset_envelope,
        video,
        output_duration_s=output_duration_s,
        preset=preset,
        features=features,
        sections=sections,
        hop_length=hop_length,
        sr=sr,
        output_fps=output_fps,
    )


def plan_speed_options(
    timeline: AudioTimeline,
    onset_envelope: np.ndarray,
    video: MediaInfo,
    *,
    output_duration_s: float,
    base_config: SpeedRampConfig,
    features: BeatSyncFeatures | None = None,
    sections: list[MusicSection] | None = None,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
    output_fps: float = DEFAULT_OUTPUT_FPS,
    styles: tuple[str, ...] | None = None,
    resolve_overrides: dict[str, float | int | str | None] | None = None,
) -> SpeedRampOptionSet:
    """Compute all hook-oriented speed profiles for UI comparison."""
    style_ids = styles or tuple(PRESETS.keys())
    options: list[SpeedRampOption] = []
    for style in style_ids:
        preset = resolve_params(base_config, style, overrides=resolve_overrides)
        plan = _plan_with_preset(
            timeline,
            onset_envelope,
            video,
            output_duration_s=output_duration_s,
            preset=preset,
            features=features,
            sections=sections,
            hop_length=hop_length,
            sr=sr,
            output_fps=output_fps,
        )
        options.append(
            SpeedRampOption(
                style=style,
                label=preset.label,
                description=preset.description,
                plan=plan,
            )
        )
    selected = base_config.style if base_config.style in PRESETS else style_ids[0]
    return SpeedRampOptionSet(selected_style=selected, options=options)
