export const MIN_SCOPE_WIDTH = 960;
export const SCOPE_PIXELS_PER_SECOND = 8;

export function scopeWidth(durationS: number): number {
  if (durationS <= 0) {
    return MIN_SCOPE_WIDTH;
  }
  return Math.max(MIN_SCOPE_WIDTH, Math.ceil(durationS * SCOPE_PIXELS_PER_SECOND));
}
