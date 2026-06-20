import type { ScopeLaneSeries, Transient, WaveformPoint } from "../types";

export type FxMarkerKind = "zoom" | "rotate";

export interface FxMarker {
  timeS: number;
  kind: FxMarkerKind;
  magnitude: number;
  reason?: string;
}

const MERGE_WINDOW_S = 0.05;
const INTERRUPT_MIN_GAP_S = 3.0;
const INTERRUPT_MAX_GAP_S = 5.0;
const EARLY_HOOK_FX_BY_S = 2.0;
const PEAK_SNAP_TOLERANCE_S = 0.15;

function zoomMagnitude(amplitude: number): number {
  const amp = Math.max(0, Math.min(1, amplitude));
  return 1.05 + amp * (1.08 - 1.05);
}

function rotateMagnitude(amplitude: number): number {
  const amp = Math.max(0, Math.min(1, amplitude));
  return Math.max(0.1, amp * 1.5);
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

function energyPeaks(
  lanes: ScopeLaneSeries[] | undefined,
  downbeats: number[],
  musicStartS: number,
  musicEndS: number,
): Array<{ timeS: number; magnitude: number; onDownbeat: boolean }> {
  const rms = lanePoints(lanes, "rms");
  const build = lanePoints(lanes, "build");
  const dropSalience = lanePoints(lanes, "drop_salience");
  const signal =
    dropSalience.length > 0
      ? dropSalience
      : build.length > 0
        ? build.map((point, index) => ({
            t: point.t,
            v: point.v * 0.6 + (rms[index]?.v ?? 0) * 0.4,
          }))
        : rms;
  const window = signal.filter((point) => point.t >= musicStartS && point.t < musicEndS);
  const windowMax = window.reduce((max, point) => Math.max(max, point.v), 0);
  const peaks = localMaxima(window)
    .filter((point) => windowMax <= 0 || point.v >= windowMax * 0.35)
    .map((point) => {
      const snapped = snapToDownbeat(point.t, downbeats);
      return {
        timeS: snapped.timeS - musicStartS,
        magnitude: snapped.onDownbeat ? Math.min(1, point.v + 0.08) : point.v,
        onDownbeat: snapped.onDownbeat,
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

function planPolicyMarkers(
  lanes: ScopeLaneSeries[] | undefined,
  downbeats: number[],
  musicStartS: number,
  musicEndS: number,
): FxMarker[] {
  const duration = musicEndS - musicStartS;
  const absDownbeats = downbeats.filter((t) => t >= musicStartS && t < musicEndS);
  const zoomCandidates = energyPeaks(lanes, absDownbeats, musicStartS, musicEndS).map((peak) => ({
    timeS: peak.timeS,
    kind: "zoom" as const,
    magnitude: Math.round(zoomMagnitude(peak.magnitude) * 10000) / 10000,
    reason: `RMS peak @ ${(musicStartS + peak.timeS).toFixed(2)}s${peak.onDownbeat ? " on downbeat" : ""}`,
  }));
  const rotateCandidates = fluxPeaks(lanes, "low", musicStartS, musicEndS)
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

function mergeNearby(events: FxMarker[]): FxMarker[] {
  if (events.length === 0) return [];
  const ordered = [...events].sort(
    (a, b) => a.timeS - b.timeS || a.kind.localeCompare(b.kind),
  );
  const merged: FxMarker[] = [ordered[0]];
  for (const event of ordered.slice(1)) {
    const prev = merged[merged.length - 1];
    if (event.kind === prev.kind && event.timeS - prev.timeS <= MERGE_WINDOW_S) {
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

  const perBucket = new Map<number, FxMarker[]>();
  for (const event of events) {
    const bucket = Math.floor(event.timeS);
    const bucketEvents = perBucket.get(bucket) ?? [];
    bucketEvents.push(event);
    perBucket.set(bucket, bucketEvents);
  }

  const limit = Math.max(1, Math.floor(maxEventsPerSecond));
  const capped: FxMarker[] = [];
  for (const bucket of [...perBucket.keys()].sort((a, b) => a - b)) {
    const bucketEvents = perBucket.get(bucket) ?? [];
    bucketEvents.sort((a, b) => b.magnitude - a.magnitude);
    capped.push(...bucketEvents.slice(0, limit));
  }
  return capped.sort((a, b) => a.timeS - b.timeS || a.kind.localeCompare(b.kind));
}

export function planSpatialFxMarkers(
  transients: Transient[],
  options: {
    musicStartS: number;
    musicEndS: number;
    maxEventsPerSecond: number;
    enabled: boolean;
    lanes?: ScopeLaneSeries[];
    downbeats?: number[];
  },
): FxMarker[] {
  if (!options.enabled) return [];

  let events: FxMarker[] = [];
  if (options.lanes && options.lanes.length > 0 && options.downbeats) {
    events = planPolicyMarkers(
      options.lanes,
      options.downbeats,
      options.musicStartS,
      options.musicEndS,
    );
  } else {
    for (const transient of transients) {
      const absoluteS = transient.timestamp_ms / 1000;
      if (absoluteS < options.musicStartS || absoluteS >= options.musicEndS) {
        continue;
      }
      for (const event of transientEvents(transient)) {
        events.push({
          ...event,
          timeS: absoluteS - options.musicStartS,
        });
      }
    }
  }

  return capEventsPerSecond(mergeNearby(events), options.maxEventsPerSecond);
}

export function countSpatialFxMarkers(markers: FxMarker[]): { zoom: number; rotate: number } {
  let zoom = 0;
  let rotate = 0;
  for (const marker of markers) {
    if (marker.kind === "zoom") zoom += 1;
    else rotate += 1;
  }
  return { zoom, rotate };
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
