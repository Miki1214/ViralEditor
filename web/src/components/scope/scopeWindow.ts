import type { ChromaGram, WaveformPoint } from "../../types";

export interface ScopeWindow {
  startS: number;
  endS: number;
}

export function windowDuration(window: ScopeWindow): number {
  return Math.max(window.endS - window.startS, 0);
}

export function cropPointsToWindow(
  points: WaveformPoint[],
  window: ScopeWindow,
): WaveformPoint[] {
  return points
    .filter((point) => point.t >= window.startS - 0.001 && point.t <= window.endS + 0.001)
    .map((point) => ({ t: point.t - window.startS, v: point.v }));
}

export function cropTimesToWindow(times: number[], window: ScopeWindow): number[] {
  return times
    .filter((timeS) => timeS >= window.startS - 0.001 && timeS <= window.endS + 0.001)
    .map((timeS) => timeS - window.startS);
}

export function cropChromaToWindow(chroma: ChromaGram, window: ScopeWindow): ChromaGram {
  const frames: number[][] = [];
  const times: number[] = [];
  for (let index = 0; index < chroma.times.length; index += 1) {
    const absolute = chroma.times[index];
    if (absolute == null || absolute < window.startS - 0.001 || absolute > window.endS + 0.001) {
      continue;
    }
    times.push(absolute - window.startS);
    frames.push(chroma.frames[index] ?? []);
  }
  return {
    ...chroma,
    times,
    frames,
  };
}

export function timeToX(
  timeS: number,
  durationS: number,
  padX: number,
  innerW: number,
): number {
  if (durationS <= 0) return padX;
  return padX + (timeS / durationS) * innerW;
}

export function xToTime(
  x: number,
  durationS: number,
  padX: number,
  innerW: number,
): number {
  if (innerW <= 0) return 0;
  const ratio = Math.max(0, Math.min(1, (x - padX) / innerW));
  return ratio * durationS;
}

/** Drop times closer than minSpacingPx (keep earlier entries). */
export function decimateTimesBySpacing(
  times: number[],
  durationS: number,
  padX: number,
  innerW: number,
  minSpacingPx: number,
): number[] {
  if (times.length === 0 || durationS <= 0 || minSpacingPx <= 0) {
    return [];
  }

  const sorted = [...times].sort((a, b) => a - b);
  const visible: number[] = [];
  let lastX = -Infinity;

  for (const timeS of sorted) {
    const x = timeToX(timeS, durationS, padX, innerW);
    if (x - lastX >= minSpacingPx) {
      visible.push(timeS);
      lastX = x;
    }
  }

  return visible;
}
