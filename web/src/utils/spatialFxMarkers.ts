import type { Transient } from "../types";

export type FxMarkerKind = "zoom" | "rotate";

export interface FxMarker {
  timeS: number;
  kind: FxMarkerKind;
  magnitude: number;
}

const MERGE_WINDOW_S = 0.05;

function zoomMagnitude(amplitude: number): number {
  const amp = Math.max(0, Math.min(1, amplitude));
  return 1.05 + amp * (1.08 - 1.05);
}

function rotateMagnitude(amplitude: number): number {
  const amp = Math.max(0, Math.min(1, amplitude));
  return Math.max(0.1, amp * 1.5);
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
      },
    ];
  }
  if (transient.type === "bass") {
    return [
      {
        timeS,
        kind: "rotate",
        magnitude: Math.round(rotateMagnitude(amp) * 10000) / 10000,
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
  },
): FxMarker[] {
  if (!options.enabled) return [];

  const events: FxMarker[] = [];
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
