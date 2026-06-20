import type { WaveformPoint } from "../../types";

/** Preserve peaks when drawing envelopes across fewer pixels than source points. */
export function resamplePointsToPixelWidth(
  points: WaveformPoint[],
  pixelWidth: number,
): WaveformPoint[] {
  if (points.length === 0) {
    return [];
  }

  const targetCount = Math.max(2, Math.floor(pixelWidth));
  if (points.length <= targetCount) {
    return points;
  }

  const bucketSize = points.length / targetCount;
  const resampled: WaveformPoint[] = [];

  for (let bucket = 0; bucket < targetCount; bucket += 1) {
    const start = Math.floor(bucket * bucketSize);
    const end = Math.min(points.length, Math.floor((bucket + 1) * bucketSize));
    if (start >= end) {
      continue;
    }

    let peak = points[start]!;
    for (let index = start + 1; index < end; index += 1) {
      const point = points[index]!;
      if (point.v > peak.v) {
        peak = point;
      }
    }
    resampled.push(peak);
  }

  return resampled;
}
