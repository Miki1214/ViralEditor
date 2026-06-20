import type { PanBeatMode, ScopeLaneSeries, Transient, WaveformPoint } from "../types";

export type FxMarkerKind = "zoom" | "rotate" | "translate";

export interface FxMarker {
  timeS: number;
  kind: FxMarkerKind;
  magnitude: number;
  direction?: number;
  reason?: string;
}

export interface PanPlanSettings {
  translateEnabled: boolean;
  panBeatMode: PanBeatMode;
  panEnergyThreshold: number;
  panEnergyFloor: number;
  panHookEnabled: boolean;
  panHookByS: number;
}

const DEFAULT_PAN_SETTINGS: PanPlanSettings = {
  translateEnabled: true,
  panBeatMode: "auto",
  panEnergyThreshold: 0.45,
  panEnergyFloor: 0.2,
  panHookEnabled: true,
  panHookByS: 1.0,
};

const SURGE_SCORE_THRESHOLD = 0.45;
const SURGE_MAGNITUDE_BOOST = 0.12;
const MERGE_WINDOW_S = 0.05;
const TAIL_PAN_LOOKBACK_S = 2.0;

export function blockDurationS(
  musicStartS: number,
  musicEndS: number,
  totalDurationS: number,
): number {
  return Math.max(totalDurationS, musicEndS - musicStartS);
}

export function blockWindowEndS(
  musicStartS: number,
  musicEndS: number,
  totalDurationS: number,
): number {
  return musicStartS + blockDurationS(musicStartS, musicEndS, totalDurationS);
}

function clampBlockTimeS(relTs: number, duration: number): number | null {
  if (relTs < -1e-6 || relTs > duration + 1e-6) {
    return null;
  }
  return Math.max(0, Math.min(duration, relTs));
}

function inBlockWindow(absT: number, musicStartS: number, windowEndS: number): boolean {
  return absT >= musicStartS - 1e-6 && absT <= windowEndS + 1e-6;
}
const INTERRUPT_MIN_GAP_S = 3.0;
const INTERRUPT_MAX_GAP_S = 5.0;
const EARLY_HOOK_FX_BY_S = 2.0;
const PEAK_SNAP_TOLERANCE_S = 0.15;
const PAN_BEAT_MIN_GAP_S = 0.25;
const PAN_DOWNBEAT_MIN_GAP_S = 0.5;
const PAN_MAGNITUDE_MIN = 0.35;
const PAN_MAGNITUDE_MAX = 1.0;

function zoomMagnitude(amplitude: number): number {
  const amp = Math.max(0, Math.min(1, amplitude));
  return 1.05 + amp * (1.08 - 1.05);
}

function rotateMagnitude(amplitude: number): number {
  const amp = Math.max(0, Math.min(1, amplitude));
  return Math.max(0.1, amp * 1.5);
}

function panMagnitude(amplitude: number): number {
  const amp = Math.max(0, Math.min(1, amplitude));
  return PAN_MAGNITUDE_MIN + amp * (PAN_MAGNITUDE_MAX - PAN_MAGNITUDE_MIN);
}

function laneAmplitudeAt(
  lanes: ScopeLaneSeries[] | undefined,
  timeS: number,
): number {
  const rms = lanePoints(lanes, "rms");
  const bandLow = lanePoints(lanes, "band_low");
  const rmsVal = rms.length > 0 ? sampleLane(rms, timeS) : 0.5;
  const lowVal = bandLow.length > 0 ? sampleLane(bandLow, timeS) : rmsVal;
  return rmsVal * 0.65 + lowVal * 0.35;
}

function lanePoints(lanes: ScopeLaneSeries[] | undefined, id: string): WaveformPoint[] {
  return lanes?.find((lane) => lane.id === id)?.points ?? [];
}

function sampleLane(points: WaveformPoint[], timeS: number): number {
  if (points.length === 0) return 0;
  let best = points[0];
  for (const point of points) {
    if (Math.abs(point.t - timeS) < Math.abs(best.t - timeS)) {
      best = point;
    }
  }
  return best.v;
}

function localMaxima(points: WaveformPoint[], minProminence = 0.08): WaveformPoint[] {
  if (points.length < 3) return [];
  const peaks: WaveformPoint[] = [];
  for (let index = 1; index < points.length - 1; index += 1) {
    const prev = points[index - 1];
    const current = points[index];
    const next = points[index + 1];
    if (current.v < prev.v || current.v < next.v) continue;
    const leftMin = Math.min(...points.slice(Math.max(0, index - 4), index).map((p) => p.v));
    const rightMin = Math.min(...points.slice(index + 1, Math.min(points.length, index + 5)).map((p) => p.v));
    if (current.v - Math.max(leftMin, rightMin) >= minProminence) {
      peaks.push(current);
    }
  }
  return peaks;
}

function snapToDownbeat(timeS: number, downbeats: number[]): { timeS: number; onDownbeat: boolean } {
  if (downbeats.length === 0) return { timeS, onDownbeat: false };
  let nearest = downbeats[0];
  for (const downbeat of downbeats) {
    if (Math.abs(downbeat - timeS) < Math.abs(nearest - timeS)) {
      nearest = downbeat;
    }
  }
  if (Math.abs(nearest - timeS) <= PEAK_SNAP_TOLERANCE_S) {
    return { timeS: nearest, onDownbeat: true };
  }
  return { timeS, onDownbeat: false };
}

function surgeCandidatePoints(
  points: WaveformPoint[],
  threshold = SURGE_SCORE_THRESHOLD,
  halfWindow = 3,
): WaveformPoint[] {
  const candidates: WaveformPoint[] = [];
  for (let index = 0; index < points.length; index += 1) {
    const current = points[index];
    if (current.v < threshold) continue;
    const lo = Math.max(0, index - halfWindow);
    const hi = Math.min(points.length, index + halfWindow + 1);
    const localMax = Math.max(...points.slice(lo, hi).map((point) => point.v));
    if (current.v >= localMax - 1e-6) {
      candidates.push(current);
    }
  }
  return candidates;
}

function energyPeaks(
  lanes: ScopeLaneSeries[] | undefined,
  downbeats: number[],
  musicStartS: number,
  musicEndS: number,
): Array<{ timeS: number; magnitude: number; onDownbeat: boolean; surgeScore: number }> {
  const rms = lanePoints(lanes, "rms");
  const build = lanePoints(lanes, "build");
  const dropSalience = lanePoints(lanes, "drop_salience");
  const surge = lanePoints(lanes, "surge");
  const surgeNorm = surge.length > 0 ? surge : null;
  let signal =
    dropSalience.length > 0
      ? dropSalience
      : surgeNorm
        ? surgeNorm.map((point, index) => ({
            t: point.t,
            v: point.v * 0.6 + (rms[index]?.v ?? 0) * 0.4,
          }))
        : build.length > 0
          ? build.map((point, index) => ({
              t: point.t,
              v: point.v * 0.6 + (rms[index]?.v ?? 0) * 0.4,
            }))
          : rms;
  if (dropSalience.length > 0 && surgeNorm) {
    signal = signal.map((point, index) => ({
      t: point.t,
      v: point.v * 0.65 + (surgeNorm[index]?.v ?? 0) * 0.35,
    }));
  }
  const window = signal.filter((point) => point.t >= musicStartS && point.t < musicEndS);
  const windowMax = window.reduce((max, point) => Math.max(max, point.v), 0);
  const surgeWindow = surgeNorm?.filter((point) => point.t >= musicStartS && point.t < musicEndS) ?? [];
  const candidatePoints = [
    ...localMaxima(window),
    ...(surgeWindow.length > 0 ? surgeCandidatePoints(surgeWindow) : []),
  ].filter(
    (point, index, list) =>
      list.findIndex((other) => Math.abs(other.t - point.t) < 0.02) === index,
  );
  const peaks = candidatePoints
    .filter((point) => windowMax <= 0 || sampleLane(window, point.t) >= windowMax * 0.35)
    .map((point) => {
      const snapped = snapToDownbeat(point.t, downbeats);
      const signalVal = sampleLane(window, point.t);
      const surgeScore = surgeNorm ? sampleLane(surgeNorm, point.t) : 0;
      let magnitude = snapped.onDownbeat ? Math.min(1, signalVal + 0.08) : signalVal;
      if (surgeScore >= SURGE_SCORE_THRESHOLD) {
        magnitude = Math.min(1, magnitude + surgeScore * SURGE_MAGNITUDE_BOOST);
      }
      return {
        timeS: snapped.timeS - musicStartS,
        magnitude,
        onDownbeat: snapped.onDownbeat,
        surgeScore,
      };
    });
  peaks.sort((a, b) => b.magnitude - a.magnitude || a.timeS - b.timeS);
  return peaks.filter(
    (peak, index, list) =>
      list.findIndex((other) => Math.abs(other.timeS - peak.timeS) < 0.08) === index,
  );
}

function fluxPeaks(
  lanes: ScopeLaneSeries[] | undefined,
  band: "low" | "high",
  musicStartS: number,
  musicEndS: number,
): Array<{ timeS: number; magnitude: number }> {
  const flux = lanePoints(lanes, band === "low" ? "flux_low" : "flux_high");
  return localMaxima(
    flux.filter((point) => point.t >= musicStartS && point.t < musicEndS),
    0.06,
  ).map((point) => ({
    timeS: point.t - musicStartS,
    magnitude: point.v,
  }));
}

function surgeAt(lanes: ScopeLaneSeries[] | undefined, timeS: number): number {
  return sampleLane(lanePoints(lanes, "surge"), timeS);
}

type PanEnergyTier = "dense" | "sparse" | "off";

function panEnergyTier(
  lanes: ScopeLaneSeries[] | undefined,
  timeS: number,
  energyThreshold: number,
  energyFloor: number,
): PanEnergyTier {
  const amp = laneAmplitudeAt(lanes, timeS);
  const surge = surgeAt(lanes, timeS);
  if (surge >= SURGE_SCORE_THRESHOLD || amp >= energyThreshold) {
    return "dense";
  }
  if (amp >= energyFloor) {
    return "sparse";
  }
  return "off";
}

function isDownbeatTime(timeS: number, downbeats: number[]): boolean {
  return downbeats.some((downbeat) => Math.abs(timeS - downbeat) <= PEAK_SNAP_TOLERANCE_S);
}

function ensureHookPan(
  selected: FxMarker[],
  lanes: ScopeLaneSeries[] | undefined,
  beatTimes: number[],
  downbeatTimes: number[],
  musicStartS: number,
  duration: number,
  panHookEnabled: boolean,
  panHookByS: number,
): FxMarker[] {
  if (!panHookEnabled) {
    return selected;
  }
  if (selected.some((event) => event.timeS <= panHookByS + 1e-6)) {
    return selected;
  }

  const hookDeadline = musicStartS + panHookByS;
  const hookCandidates = (beatTimes.length > 0 ? beatTimes : downbeatTimes).filter(
    (t) => t >= musicStartS - 1e-6 && t <= hookDeadline + 1e-6,
  );
  const hookAbs =
    hookCandidates[0] ?? musicStartS + Math.min(0.5, duration * 0.25);
  const relTs = clampBlockTimeS(hookAbs - musicStartS, duration);
  if (relTs == null) {
    return selected;
  }

  const amp = laneAmplitudeAt(lanes, hookAbs);
  const hookAmp = Math.max(amp, 0.35);
  return [
    ...selected,
    {
      timeS: relTs,
      kind: "translate",
      magnitude: Math.round(panMagnitude(hookAmp) * 10000) / 10000,
      direction: 1,
      reason: `Hook pan @ ${hookAbs.toFixed(2)}s`,
    },
  ].sort((a, b) => a.timeS - b.timeS);
}

function ensureSlotBoundaryPans(
  selected: FxMarker[],
  lanes: ScopeLaneSeries[] | undefined,
  slotBoundaryTimesAbs: number[],
  musicStartS: number,
  duration: number,
): FxMarker[] {
  if (slotBoundaryTimesAbs.length === 0) {
    return selected;
  }

  const merged = [...selected];
  let direction = 1;
  const last = merged[merged.length - 1];
  if (last?.direction) {
    direction = -last.direction;
  }

  for (const absT of [...slotBoundaryTimesAbs].sort((a, b) => a - b)) {
    const relTs = clampBlockTimeS(absT - musicStartS, duration);
    if (relTs == null || relTs <= 1e-6) {
      continue;
    }
    if (merged.some((event) => Math.abs(event.timeS - relTs) < PAN_BEAT_MIN_GAP_S - 0.01)) {
      continue;
    }

    const amp = laneAmplitudeAt(lanes, absT);
    const hookAmp = Math.max(amp, 0.35);
    merged.push({
      timeS: relTs,
      kind: "translate",
      magnitude: Math.round(panMagnitude(hookAmp) * 10000) / 10000,
      direction,
      reason: `Slot entry pan @ ${absT.toFixed(2)}s`,
    });
    direction *= -1;
  }

  return merged.sort((a, b) => a.timeS - b.timeS);
}

function ensureTailBeatPans(
  selected: FxMarker[],
  lanes: ScopeLaneSeries[] | undefined,
  beatTimesAbs: number[],
  musicStartS: number,
  duration: number,
): FxMarker[] {
  if (duration <= 0 || beatTimesAbs.length === 0) {
    return selected;
  }

  const merged = [...selected];
  let direction = 1;
  const last = merged[merged.length - 1];
  if (last?.direction) {
    direction = -last.direction;
  }

  const tailStart = Math.max(0, duration - TAIL_PAN_LOOKBACK_S);
  for (const absT of [...beatTimesAbs].sort((a, b) => a - b)) {
    const relTs = clampBlockTimeS(absT - musicStartS, duration);
    if (relTs == null || relTs < tailStart - 1e-6) {
      continue;
    }
    if (merged.some((event) => Math.abs(event.timeS - relTs) < PAN_BEAT_MIN_GAP_S - 0.01)) {
      continue;
    }

    const amp = laneAmplitudeAt(lanes, absT);
    const hookAmp = Math.max(amp, 0.35);
    merged.push({
      timeS: relTs,
      kind: "translate",
      magnitude: Math.round(panMagnitude(hookAmp) * 10000) / 10000,
      direction,
      reason: `Tail pan @ ${absT.toFixed(2)}s`,
    });
    direction *= -1;
  }

  return merged.sort((a, b) => a.timeS - b.timeS);
}

function planTranslationMarkers(
  lanes: ScopeLaneSeries[] | undefined,
  downbeats: number[],
  beats: number[],
  musicStartS: number,
  windowEndS: number,
  duration: number,
  pan: PanPlanSettings,
  slotBoundaryTimesAbs: number[] = [],
): FxMarker[] {
  if (!pan.translateEnabled) {
    return [];
  }

  if (duration <= 0) return [];

  const downbeatTimes = downbeats.filter((t) => inBlockWindow(t, musicStartS, windowEndS));
  const beatTimes = beats.filter((t) => inBlockWindow(t, musicStartS, windowEndS));

  let candidates: number[];
  if (pan.panBeatMode === "downbeats") {
    candidates = downbeatTimes;
  } else if (pan.panBeatMode === "beats") {
    candidates = beatTimes.length > 0 ? beatTimes : downbeatTimes;
  } else {
    candidates = beatTimes.length > 0 ? beatTimes : downbeatTimes;
  }

  if (candidates.length === 0) {
    const step = Math.max(PAN_DOWNBEAT_MIN_GAP_S, duration / 8);
    candidates = [];
    for (let t = musicStartS; t < windowEndS - 1e-6; t += step) {
      candidates.push(t);
    }
  }

  const selected: FxMarker[] = [];
  let direction = 1;
  let lastRel = -PAN_BEAT_MIN_GAP_S;
  for (const absT of [...candidates].sort((a, b) => a - b)) {
    const tier = panEnergyTier(
      lanes,
      absT,
      pan.panEnergyThreshold,
      pan.panEnergyFloor,
    );
    if (tier === "off") continue;

    if (pan.panBeatMode === "auto" && tier === "sparse" && !isDownbeatTime(absT, downbeatTimes)) {
      continue;
    }
    if (pan.panBeatMode === "downbeats" && !isDownbeatTime(absT, downbeatTimes)) {
      continue;
    }

    const relTs = clampBlockTimeS(absT - musicStartS, duration);
    if (relTs == null) continue;

    const minGap =
      tier === "dense" || pan.panBeatMode === "beats"
        ? PAN_BEAT_MIN_GAP_S
        : PAN_DOWNBEAT_MIN_GAP_S;
    if (relTs - lastRel < minGap - 0.01) continue;

    const amp = laneAmplitudeAt(lanes, absT);
    const tierLabel = tier === "dense" ? "beat" : "downbeat";
    selected.push({
      timeS: relTs,
      kind: "translate",
      magnitude: Math.round(panMagnitude(amp) * 10000) / 10000,
      direction,
      reason: `Pan (${tierLabel}) @ ${absT.toFixed(2)}s`,
    });
    direction *= -1;
    lastRel = relTs;
  }

  return ensureTailBeatPans(
    ensureSlotBoundaryPans(
      ensureHookPan(
        selected,
        lanes,
        beatTimes,
        downbeatTimes,
        musicStartS,
        duration,
        pan.panHookEnabled,
        pan.panHookByS,
      ),
      lanes,
      slotBoundaryTimesAbs,
      musicStartS,
      duration,
    ),
    lanes,
    beatTimes.length > 0 ? beatTimes : downbeatTimes,
    musicStartS,
    duration,
  );
}

function planPolicyMarkers(
  lanes: ScopeLaneSeries[] | undefined,
  downbeats: number[],
  beats: number[],
  musicStartS: number,
  windowEndS: number,
  duration: number,
  pan: PanPlanSettings = DEFAULT_PAN_SETTINGS,
  slotBoundaryTimesAbs: number[] = [],
): FxMarker[] {
  const absDownbeats = downbeats.filter((t) => inBlockWindow(t, musicStartS, windowEndS));
  const zoomCandidates = energyPeaks(lanes, absDownbeats, musicStartS, windowEndS).map((peak) => ({
    timeS: peak.timeS,
    kind: "zoom" as const,
    magnitude: Math.round(zoomMagnitude(peak.magnitude) * 10000) / 10000,
    reason:
      peak.surgeScore >= SURGE_SCORE_THRESHOLD
        ? `Energy surge @ ${(musicStartS + peak.timeS).toFixed(2)}s${peak.onDownbeat ? " on downbeat" : ""}`
        : `RMS peak @ ${(musicStartS + peak.timeS).toFixed(2)}s${peak.onDownbeat ? " on downbeat" : ""}`,
  }));
  const rotateCandidates = fluxPeaks(lanes, "low", musicStartS, windowEndS)
    .filter((peak) => !zoomCandidates.some((zoom) => Math.abs(zoom.timeS - peak.timeS) <= 0.12))
    .map((peak) => ({
      timeS: peak.timeS,
      kind: "rotate" as const,
      magnitude: Math.round(rotateMagnitude(peak.magnitude) * 10000) / 10000,
      reason: `Low-band flux @ ${(musicStartS + peak.timeS).toFixed(2)}s`,
    }));

  const selected: FxMarker[] = [];
  let cursor = 0;
  const hookZoom = zoomCandidates.find((event) => event.timeS <= EARLY_HOOK_FX_BY_S);
  if (hookZoom) {
    selected.push(hookZoom);
    cursor = hookZoom.timeS;
  }

  while (cursor < duration - 0.5) {
    const nextDue = cursor + INTERRUPT_MIN_GAP_S;
    const pool = [...zoomCandidates, ...rotateCandidates]
      .filter(
        (event) =>
          event.timeS >= nextDue - 0.05 &&
          selected.every((kept) => Math.abs(kept.timeS - event.timeS) >= INTERRUPT_MIN_GAP_S),
      )
      .sort((a, b) => a.timeS - b.timeS || b.magnitude - a.magnitude);
    if (pool.length === 0) break;
    selected.push(pool[0]);
    cursor = pool[0].timeS;
    if (selected.length > 1 && cursor - selected[selected.length - 2].timeS > INTERRUPT_MAX_GAP_S) {
      continue;
    }
  }

  selected.push(
    ...planTranslationMarkers(
      lanes,
      downbeats,
      beats,
      musicStartS,
      windowEndS,
      duration,
      pan,
      slotBoundaryTimesAbs,
    ),
  );

  return selected.sort((a, b) => a.timeS - b.timeS);
}

function transientEvents(transient: Transient): FxMarker[] {
  const timeS = transient.timestamp_ms / 1000;
  const amp = transient.amplitude_normalized;

  if (transient.type === "drop") {
    return [
      {
        timeS,
        kind: "zoom",
        magnitude: Math.round(zoomMagnitude(amp) * 10000) / 10000,
        reason: `Onset drop @ ${timeS.toFixed(2)}s`,
      },
    ];
  }
  if (transient.type === "bass") {
    return [
      {
        timeS,
        kind: "rotate",
        magnitude: Math.round(rotateMagnitude(amp) * 10000) / 10000,
        reason: `Bass hit @ ${timeS.toFixed(2)}s`,
      },
    ];
  }
  return [];
}

function mergeKey(marker: FxMarker): string {
  if (marker.kind === "translate") {
    return `${marker.kind}:${marker.direction ?? 0}`;
  }
  return marker.kind;
}

function mergeNearby(events: FxMarker[]): FxMarker[] {
  if (events.length === 0) return [];
  const ordered = [...events].sort(
    (a, b) => a.timeS - b.timeS || a.kind.localeCompare(b.kind),
  );
  const merged: FxMarker[] = [ordered[0]];
  for (const event of ordered.slice(1)) {
    const prev = merged[merged.length - 1];
    if (
      mergeKey(event) === mergeKey(prev) &&
      event.timeS - prev.timeS <= MERGE_WINDOW_S
    ) {
      if (event.magnitude >= prev.magnitude) {
        merged[merged.length - 1] = event;
      }
      continue;
    }
    merged.push(event);
  }
  return merged;
}

function capEventsPerSecond(events: FxMarker[], maxEventsPerSecond: number): FxMarker[] {
  if (maxEventsPerSecond <= 0 || events.length === 0) return events;

  const limit = Math.max(1, Math.floor(maxEventsPerSecond));
  const kinds: FxMarkerKind[] = ["zoom", "rotate", "translate"];
  const capped: FxMarker[] = [];

  for (const kind of kinds) {
    const kindEvents = events.filter((event) => event.kind === kind);
    if (kindEvents.length === 0) continue;

    const perBucket = new Map<number, FxMarker[]>();
    for (const event of kindEvents) {
      const bucket = Math.floor(event.timeS);
      const bucketEvents = perBucket.get(bucket) ?? [];
      bucketEvents.push(event);
      perBucket.set(bucket, bucketEvents);
    }

    for (const bucket of [...perBucket.keys()].sort((a, b) => a - b)) {
      const bucketEvents = perBucket.get(bucket) ?? [];
      bucketEvents.sort((a, b) => b.magnitude - a.magnitude);
      capped.push(...bucketEvents.slice(0, limit));
    }
  }

  return capped.sort((a, b) => a.timeS - b.timeS || a.kind.localeCompare(b.kind));
}

export function assignedSlotBoundaryTimesAbs(
  slots: Array<{
    out_start_s: number;
    out_end_s: number;
    assigned_clip_id: string | null;
  }>,
  musicStartS: number,
  windowEndS: number,
): number[] {
  const boundaries: number[] = [];
  for (const slot of slots) {
    if (!slot.assigned_clip_id) continue;
    for (const edgeS of [slot.out_start_s, slot.out_end_s]) {
      if (edgeS <= 1e-6) continue;
      const absT = musicStartS + edgeS;
      if (inBlockWindow(absT, musicStartS, windowEndS)) {
        boundaries.push(absT);
      }
    }
  }
  return [...new Set(boundaries)].sort((a, b) => a - b);
}

export function planSpatialFxMarkers(
  transients: Transient[],
  options: {
    musicStartS: number;
    musicEndS: number;
    totalDurationS?: number;
    maxEventsPerSecond: number;
    enabled: boolean;
    lanes?: ScopeLaneSeries[];
    downbeats?: number[];
    beats?: number[];
    pan?: Partial<PanPlanSettings>;
    slotBoundaryTimesAbs?: number[];
  },
): FxMarker[] {
  if (!options.enabled) return [];

  const pan: PanPlanSettings = { ...DEFAULT_PAN_SETTINGS, ...options.pan };
  const duration = blockDurationS(
    options.musicStartS,
    options.musicEndS,
    options.totalDurationS ?? options.musicEndS - options.musicStartS,
  );
  const windowEndS = options.musicStartS + duration;
  const slotBoundaryTimesAbs =
    options.slotBoundaryTimesAbs ??
    [];

  let events: FxMarker[] = [];
  if (options.lanes && options.lanes.length > 0 && options.downbeats) {
    events = planPolicyMarkers(
      options.lanes,
      options.downbeats,
      options.beats ?? [],
      options.musicStartS,
      windowEndS,
      duration,
      pan,
      slotBoundaryTimesAbs,
    );
  } else {
    for (const transient of transients) {
      const absoluteS = transient.timestamp_ms / 1000;
      if (!inBlockWindow(absoluteS, options.musicStartS, windowEndS)) {
        continue;
      }
      for (const event of transientEvents(transient)) {
        const relTs = clampBlockTimeS(absoluteS - options.musicStartS, duration);
        if (relTs == null) continue;
        events.push({
          ...event,
          timeS: relTs,
        });
      }
    }
  }

  return capEventsPerSecond(mergeNearby(events), options.maxEventsPerSecond);
}

export function countSpatialFxMarkers(markers: FxMarker[]): {
  zoom: number;
  rotate: number;
  translate: number;
} {
  let zoom = 0;
  let rotate = 0;
  let translate = 0;
  for (const marker of markers) {
    if (marker.kind === "zoom") zoom += 1;
    else if (marker.kind === "rotate") rotate += 1;
    else translate += 1;
  }
  return { zoom, rotate, translate };
}

export function isRmsValley(
  lanes: ScopeLaneSeries[] | undefined,
  timeS: number,
  musicStartS: number,
  musicEndS: number,
): boolean {
  const rms = lanePoints(lanes, "rms").filter(
    (point) => point.t >= musicStartS && point.t < musicEndS,
  );
  if (rms.length === 0) return false;
  const value = sampleLane(rms, timeS);
  const peak = rms.reduce((max, point) => Math.max(max, point.v), 0);
  return peak > 0 && value < peak * 0.35;
}
