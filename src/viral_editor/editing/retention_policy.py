"""Research-backed retention editing policy — single source for FX, slots, and blocks."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from pydantic import Field

from viral_editor.models import DomainModel, FxKind, RetentionPlanScore, Transient, TransientType

# Pattern-interrupt cadence (3–5 s) and hook window heuristics from short-form retention research.
INTERRUPT_MIN_GAP_S = 3.0
INTERRUPT_MAX_GAP_S = 5.0
HOOK_WINDOW_S = 3.0
EARLY_HOOK_FX_BY_S = 2.0
PEAK_SNAP_TOLERANCE_S = 0.15
TRANSIENT_ALIGN_TOLERANCE_S = 0.12
BASS_BAND_RATIO = 0.6
DEFAULT_HOP_LENGTH = 512
DEFAULT_SR = 22050


class PlannedInterrupt(DomainModel):
    """One pattern interrupt (zoom or rotate) with human-readable rationale."""

    timestamp_s: float = Field(ge=0)
    kind: FxKind
    magnitude: float = Field(gt=0)
    reason: str


@dataclass(frozen=True)
class _Peak:
    time_s: float
    magnitude: float
    on_downbeat: bool
    frame: int


def _time_to_frame(time_s: float, *, hop_length: int, sr: int) -> int:
    return int(round(time_s * sr / hop_length))


def _frame_to_time(frame: int, *, hop_length: int, sr: int) -> float:
    return frame * hop_length / sr


def _lane_array(
    scope_lanes: dict[str, np.ndarray] | None,
    key: str,
) -> np.ndarray | None:
    if not scope_lanes:
        return None
    lane = scope_lanes.get(key)
    if lane is None or lane.size == 0:
        return None
    return lane.astype(float)


def _normalize_lane(lane: np.ndarray) -> np.ndarray:
    peak = float(lane.max()) if lane.size else 1.0
    if peak <= 1e-9:
        return np.zeros_like(lane)
    return lane / peak


def _local_maxima(signal: np.ndarray, *, min_prominence: float = 0.08) -> list[int]:
    if signal.size < 3:
        return []
    peaks: list[int] = []
    for index in range(1, signal.size - 1):
        if signal[index] < signal[index - 1] or signal[index] < signal[index + 1]:
            continue
        left = float(signal[max(0, index - 4) : index].min()) if index else 0.0
        right = float(signal[index + 1 : min(signal.size, index + 5)].min())
        prominence = float(signal[index]) - max(left, right)
        if prominence >= min_prominence:
            peaks.append(index)
    return peaks


def _snap_to_downbeat(
    time_s: float,
    downbeats: list[float] | np.ndarray,
    *,
    tolerance_s: float = PEAK_SNAP_TOLERANCE_S,
) -> tuple[float, bool]:
    if len(downbeats) == 0:
        return time_s, False
    nearest = min(downbeats, key=lambda t: abs(float(t) - time_s))
    if abs(float(nearest) - time_s) <= tolerance_s:
        return float(nearest), True
    return time_s, False


def find_energy_peaks(
    scope_lanes: dict[str, np.ndarray] | None,
    downbeats: list[float] | np.ndarray,
    *,
    window_start_s: float = 0.0,
    window_end_s: float | None = None,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
) -> list[_Peak]:
    """Ranked RMS/build peaks snapped to nearby downbeats when possible."""
    rms = _lane_array(scope_lanes, "rms")
    build = _lane_array(scope_lanes, "build")
    drop_salience = _lane_array(scope_lanes, "drop_salience")
    if rms is None:
        return []

    if drop_salience is not None and drop_salience.size == rms.size:
        signal = _normalize_lane(drop_salience)
    elif build is not None and build.size == rms.size:
        signal = _normalize_lane(build) * 0.6 + _normalize_lane(rms) * 0.4
    else:
        signal = _normalize_lane(rms)

    end_s = window_end_s if window_end_s is not None else _frame_to_time(rms.size - 1, hop_length=hop_length, sr=sr)
    window_max = 0.0
    start_frame = _time_to_frame(window_start_s, hop_length=hop_length, sr=sr)
    end_frame = _time_to_frame(end_s, hop_length=hop_length, sr=sr)
    start_frame = max(0, min(start_frame, signal.size - 1))
    end_frame = max(start_frame + 1, min(end_frame, signal.size))
    window_slice = signal[start_frame:end_frame]
    if window_slice.size:
        window_max = float(window_slice.max())

    downbeat_list = [float(t) for t in np.asarray(downbeats).tolist()]
    peaks: list[_Peak] = []
    for frame in _local_maxima(signal):
        time_s = _frame_to_time(frame, hop_length=hop_length, sr=sr)
        if time_s < window_start_s - 1e-6 or time_s >= end_s - 1e-6:
            continue
        rms_val = float(_normalize_lane(rms)[frame]) if frame < rms.size else 0.0
        if window_max > 0 and rms_val < window_max * 0.35:
            continue
        snapped, on_downbeat = _snap_to_downbeat(time_s, downbeat_list)
        magnitude = float(signal[frame])
        if on_downbeat:
            magnitude = min(1.0, magnitude + 0.08)
        peaks.append(
            _Peak(
                time_s=snapped,
                magnitude=magnitude,
                on_downbeat=on_downbeat,
                frame=frame,
            )
        )

    peaks.sort(key=lambda peak: (-peak.magnitude, peak.time_s))
    deduped: list[_Peak] = []
    for peak in peaks:
        if all(abs(peak.time_s - kept.time_s) >= 0.08 for kept in deduped):
            deduped.append(peak)
    return deduped


def find_flux_peaks(
    scope_lanes: dict[str, np.ndarray] | None,
    band: str,
    *,
    window_start_s: float = 0.0,
    window_end_s: float | None = None,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
) -> list[_Peak]:
    """Positive spectral-flux peaks for a band (``flux_low`` or ``flux_high``)."""
    key = f"flux_{band}"
    flux = _lane_array(scope_lanes, key)
    if flux is None:
        return []

    signal = _normalize_lane(flux)
    end_s = window_end_s if window_end_s is not None else _frame_to_time(flux.size - 1, hop_length=hop_length, sr=sr)
    peaks: list[_Peak] = []
    for frame in _local_maxima(signal, min_prominence=0.06):
        time_s = _frame_to_time(frame, hop_length=hop_length, sr=sr)
        if time_s < window_start_s - 1e-6 or time_s >= end_s - 1e-6:
            continue
        peaks.append(
            _Peak(
                time_s=time_s,
                magnitude=float(signal[frame]),
                on_downbeat=False,
                frame=frame,
            )
        )
    peaks.sort(key=lambda peak: (-peak.magnitude, peak.time_s))
    return peaks


def classify_accents(
    onsets_s: np.ndarray,
    amplitudes_norm: np.ndarray,
    scope_lanes: dict[str, np.ndarray] | None,
    downbeats: list[float] | np.ndarray,
    *,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
    window_start_s: float = 0.0,
    window_end_s: float | None = None,
) -> list[Transient]:
    """Classify onsets using energy peaks + downbeats instead of global onset percentile."""
    if onsets_s.size == 0:
        return []

    energy_peaks = find_energy_peaks(
        scope_lanes,
        downbeats,
        window_start_s=window_start_s,
        window_end_s=window_end_s,
        hop_length=hop_length,
        sr=sr,
    )
    low_flux = find_flux_peaks(
        scope_lanes,
        "low",
        window_start_s=window_start_s,
        window_end_s=window_end_s,
        hop_length=hop_length,
        sr=sr,
    )

    drop_times = {round(peak.time_s, 4) for peak in energy_peaks[:12]}
    bass_times = {
        round(peak.time_s, 4)
        for peak in low_flux[:16]
        if all(abs(peak.time_s - dt) > 0.1 for dt in drop_times)
    }

    transients: list[Transient] = []
    for time_s, amplitude in zip(onsets_s, amplitudes_norm, strict=True):
        kind: TransientType = "percussive"
        amp = float(amplitude)
        frame = _time_to_frame(time_s, hop_length=hop_length, sr=sr)

        low_flux_val = 0.0
        high_flux_val = 0.0
        rms_val = 0.0
        rms = _lane_array(scope_lanes, "rms") if scope_lanes else None
        band_low = _lane_array(scope_lanes, "band_low") if scope_lanes else None
        band_high = _lane_array(scope_lanes, "band_high") if scope_lanes else None
        if scope_lanes:
            flux_low = _lane_array(scope_lanes, "flux_low")
            flux_high = _lane_array(scope_lanes, "flux_high")
            if flux_low is not None and 0 <= frame < flux_low.size:
                low_flux_val = float(flux_low[frame])
            if flux_high is not None and 0 <= frame < flux_high.size:
                high_flux_val = float(flux_high[frame])
            if rms is not None and 0 <= frame < rms.size:
                rms_val = float(rms[frame])

        band_total = 0.0
        low_band_ratio = 0.0
        if band_low is not None and band_high is not None and 0 <= frame < band_low.size:
            low_e = float(band_low[frame])
            high_e = float(band_high[frame]) if frame < band_high.size else 0.0
            band_total = low_e + high_e + 1e-9
            low_band_ratio = low_e / band_total

        for peak in energy_peaks:
            if abs(time_s - peak.time_s) <= TRANSIENT_ALIGN_TOLERANCE_S:
                low_dominant = (
                    low_band_ratio >= BASS_BAND_RATIO
                    or (
                        low_flux_val > high_flux_val * 1.15
                        and rms is not None
                        and rms.size > 0
                        and rms_val < float(np.quantile(rms, 0.7))
                    )
                )
                if low_dominant:
                    kind = "bass"
                    amp = max(amp, peak.magnitude * 0.85)
                else:
                    kind = "drop"
                    amp = max(amp, peak.magnitude)
                break

        if kind == "percussive" and low_band_ratio >= BASS_BAND_RATIO:
            kind = "bass"

        if kind == "percussive":
            for peak in low_flux:
                if abs(time_s - peak.time_s) <= TRANSIENT_ALIGN_TOLERANCE_S:
                    kind = "bass"
                    amp = max(amp, peak.magnitude * 0.85)
                    break

        transients.append(
            Transient(
                timestamp_ms=int(round(time_s * 1000.0)),
                amplitude_normalized=round(min(1.0, amp), 4),
                type=kind,
            )
        )

    transients.sort(key=lambda item: item.timestamp_ms)

    if scope_lanes and energy_peaks:
        top_peak_times = [peak.time_s for peak in energy_peaks[:3]]
        band_low = _lane_array(scope_lanes, "band_low")
        band_high = _lane_array(scope_lanes, "band_high")
        upgraded: list[Transient] = []
        for transient in transients:
            time_s = transient.timestamp_ms / 1000.0
            frame = _time_to_frame(time_s, hop_length=hop_length, sr=sr)
            low_band_ratio = 0.0
            if (
                band_low is not None
                and band_high is not None
                and 0 <= frame < band_low.size
            ):
                low_e = float(band_low[frame])
                high_e = float(band_high[frame]) if frame < band_high.size else 0.0
                low_band_ratio = low_e / (low_e + high_e + 1e-9)

            if transient.type != "drop" and any(
                abs(time_s - peak_time) <= TRANSIENT_ALIGN_TOLERANCE_S
                for peak_time in top_peak_times
            ):
                if transient.type != "bass" and low_band_ratio < BASS_BAND_RATIO:
                    upgraded.append(
                        transient.model_copy(
                            update={
                                "type": "drop",
                                "amplitude_normalized": round(
                                    min(1.0, max(transient.amplitude_normalized, 0.75)),
                                    4,
                                ),
                            }
                        )
                    )
                    continue
            upgraded.append(transient)
        transients = upgraded

    return transients


def place_interrupts(
    scope_lanes: dict[str, np.ndarray] | None,
    downbeats: list[float] | np.ndarray,
    *,
    window_start_s: float,
    window_end_s: float,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
    min_gap_s: float = INTERRUPT_MIN_GAP_S,
    max_gap_s: float = INTERRUPT_MAX_GAP_S,
) -> list[PlannedInterrupt]:
    """Place zoom/rotate interrupts on energy peaks with 3–5 s cadence and early hook."""
    duration = max(window_end_s - window_start_s, 0.0)
    if duration <= 0:
        return []

    rel_downbeats = [
        float(t) - window_start_s
        for t in np.asarray(downbeats).tolist()
        if window_start_s - 1e-6 <= float(t) < window_end_s - 1e-6
    ]

    energy_peaks = find_energy_peaks(
        scope_lanes,
        downbeats,
        window_start_s=window_start_s,
        window_end_s=window_end_s,
        hop_length=hop_length,
        sr=sr,
    )
    low_flux = find_flux_peaks(
        scope_lanes,
        "low",
        window_start_s=window_start_s,
        window_end_s=window_end_s,
        hop_length=hop_length,
        sr=sr,
    )

    zoom_candidates = [
        PlannedInterrupt(
            timestamp_s=round(peak.time_s - window_start_s, 6),
            kind="zoom",
            magnitude=round(1.05 + peak.magnitude * 0.03, 4),
            reason=(
                f"RMS peak @ {peak.time_s:.2f}s"
                + (" on downbeat" if peak.on_downbeat else "")
            ),
        )
        for peak in energy_peaks
    ]

    rotate_candidates = []
    zoom_abs_times = {peak.time_s for peak in energy_peaks}
    for peak in low_flux:
        if any(abs(peak.time_s - zt) <= 0.12 for zt in zoom_abs_times):
            continue
        rotate_candidates.append(
            PlannedInterrupt(
                timestamp_s=round(peak.time_s - window_start_s, 6),
                kind="rotate",
                magnitude=round(max(0.1, peak.magnitude * 1.5), 4),
                reason=f"Low-band flux @ {peak.time_s:.2f}s",
            )
        )

    selected: list[PlannedInterrupt] = []

    if zoom_candidates:
        hook_candidate = next(
            (event for event in zoom_candidates if event.timestamp_s <= EARLY_HOOK_FX_BY_S),
            None,
        )
        selected.append(
            hook_candidate
            or max(zoom_candidates, key=lambda event: event.magnitude)
        )

    cursor = selected[-1].timestamp_s if selected else 0.0
    while cursor < duration - 0.5:
        next_due = cursor + min_gap_s
        pool = [
            event
            for event in zoom_candidates + rotate_candidates
            if event.timestamp_s >= next_due - 0.05
            and all(abs(event.timestamp_s - kept.timestamp_s) >= min_gap_s for kept in selected)
        ]
        if not pool:
            break
        pool.sort(key=lambda event: (event.timestamp_s, -event.magnitude))
        pick = pool[0]
        selected.append(pick)
        cursor = pick.timestamp_s

    if not selected and zoom_candidates:
        selected.append(zoom_candidates[0])

    selected.sort(key=lambda event: event.timestamp_s)
    return selected


def score_plan(
    scope_lanes: dict[str, np.ndarray] | None,
    downbeats: list[float] | np.ndarray,
    interrupts: list[PlannedInterrupt],
    *,
    window_start_s: float,
    window_end_s: float,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
) -> RetentionPlanScore:
    """Score hook strength, cadence, beat sync, and energy coverage for a window."""
    duration = max(window_end_s - window_start_s, 1e-6)
    rel_downbeats = [
        float(t) - window_start_s
        for t in np.asarray(downbeats).tolist()
        if window_start_s - 1e-6 <= float(t) < window_end_s - 1e-6
    ]

    hook_zooms = [event for event in interrupts if event.kind == "zoom" and event.timestamp_s <= HOOK_WINDOW_S]
    hook_strength = 0.0
    if hook_zooms:
        earliest = min(event.timestamp_s for event in hook_zooms)
        hook_strength = 1.0 if earliest <= EARLY_HOOK_FX_BY_S else max(0.4, 1.0 - (earliest - EARLY_HOOK_FX_BY_S) / HOOK_WINDOW_S)

    gaps: list[float] = []
    for index in range(1, len(interrupts)):
        gaps.append(interrupts[index].timestamp_s - interrupts[index - 1].timestamp_s)
    cadence_adherence = 1.0
    if gaps:
        in_band = sum(1 for gap in gaps if INTERRUPT_MIN_GAP_S <= gap <= INTERRUPT_MAX_GAP_S + 0.5)
        cadence_adherence = in_band / len(gaps)

    zoom_events = [event for event in interrupts if event.kind == "zoom"]
    beat_sync = 0.0
    if zoom_events and rel_downbeats:
        synced = 0
        for event in zoom_events:
            abs_t = window_start_s + event.timestamp_s
            if any(abs(abs_t - db - window_start_s) <= PEAK_SNAP_TOLERANCE_S for db in rel_downbeats):
                synced += 1
            elif "downbeat" in event.reason:
                synced += 1
        beat_sync = synced / len(zoom_events)

    energy_peaks = find_energy_peaks(
        scope_lanes,
        downbeats,
        window_start_s=window_start_s,
        window_end_s=window_end_s,
        hop_length=hop_length,
        sr=sr,
    )
    energy_coverage = 0.0
    if energy_peaks:
        covered = sum(
            1
            for peak in energy_peaks[:8]
            if any(abs((window_start_s + event.timestamp_s) - peak.time_s) <= 0.2 for event in zoom_events)
        )
        energy_coverage = covered / min(len(energy_peaks), 8)

    overall = (
        hook_strength * 0.3
        + cadence_adherence * 0.25
        + beat_sync * 0.25
        + energy_coverage * 0.2
    )
    return RetentionPlanScore(
        overall=round(min(1.0, overall), 4),
        hook_strength=round(hook_strength, 4),
        cadence_adherence=round(cadence_adherence, 4),
        beat_sync=round(beat_sync, 4),
        energy_coverage=round(energy_coverage, 4),
    )


def select_payoff_downbeat_s(
    scope_lanes: dict[str, np.ndarray] | None,
    downbeats: list[float] | np.ndarray,
    *,
    window_start_s: float,
    window_end_s: float,
    hook_budget_s: float,
    min_s: float = 0.25,
) -> float:
    """Pick hook payoff split at highest drop-salience downbeat within budget."""
    max_s = max(min_s, hook_budget_s - min_s)
    candidates = [
        float(t) - window_start_s
        for t in np.asarray(downbeats).tolist()
        if window_start_s - 1e-6 <= float(t) < window_end_s - 1e-6
    ]
    candidates = [t for t in candidates if min_s - 1e-6 <= t <= max_s + 1e-6]
    if not candidates:
        return round(min(max(hook_budget_s * 0.5, min_s), max_s), 6)

    drop_salience = _lane_array(scope_lanes, "drop_salience")
    rms = _lane_array(scope_lanes, "rms")
    best = candidates[0]
    best_score = -1.0
    for rel_t in candidates:
        abs_t = window_start_s + rel_t
        frame = _time_to_frame(abs_t, hop_length=DEFAULT_HOP_LENGTH, sr=DEFAULT_SR)
        score = rel_t * 0.05
        if drop_salience is not None and 0 <= frame < drop_salience.size:
            score += float(drop_salience[frame]) * 2.0
        elif rms is not None and 0 <= frame < rms.size:
            score += float(rms[frame])
        if score > best_score:
            best_score = score
            best = rel_t
    return round(best, 6)


def retention_bonus_for_window(
    scope_lanes: dict[str, np.ndarray] | None,
    downbeats: list[float] | np.ndarray,
    *,
    window_start_s: float,
    window_end_s: float,
) -> float:
    """Compact 0–1 bonus for block scoring from policy metrics."""
    interrupts = place_interrupts(
        scope_lanes,
        downbeats,
        window_start_s=window_start_s,
        window_end_s=window_end_s,
    )
    plan_score = score_plan(
        scope_lanes,
        downbeats,
        interrupts,
        window_start_s=window_start_s,
        window_end_s=window_end_s,
    )
    return plan_score.overall


def pacing_density_score(
    scope_lanes: dict[str, np.ndarray] | None,
    *,
    window_start_s: float,
    window_end_s: float,
    hop_length: int = DEFAULT_HOP_LENGTH,
    sr: int = DEFAULT_SR,
) -> float:
    """Mean pacing density normalized to 0–1 inside a window."""
    pacing = _lane_array(scope_lanes, "pacing_density")
    if pacing is None:
        return 0.5
    start_frame = _time_to_frame(window_start_s, hop_length=hop_length, sr=sr)
    end_frame = _time_to_frame(window_end_s, hop_length=hop_length, sr=sr)
    start_frame = max(0, min(start_frame, pacing.size - 1))
    end_frame = max(start_frame + 1, min(end_frame, pacing.size))
    segment = pacing[start_frame:end_frame]
    if segment.size == 0:
        return 0.5
    peak = float(segment.max()) if segment.size else 1.0
    if peak <= 1e-9:
        return 0.0
    return float(segment.mean() / peak)
