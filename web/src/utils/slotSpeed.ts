import type { SlotRole } from "../types";

/** Matches `audio/storyboard.py` punch slow-mo multiplier. */
export const PUNCH_SPEED_FACTOR = 0.65;

export function slotTimestretch(cropSpanS: number, targetDurationS: number): number {
  if (targetDurationS <= 0 || cropSpanS <= 0) return 1;
  return cropSpanS / targetDurationS;
}

export function slotRenderSpeedFactor(
  cropSpanS: number,
  targetDurationS: number,
  role: SlotRole,
): number {
  const fit = slotTimestretch(cropSpanS, targetDurationS);
  return role === "punch" ? fit * PUNCH_SPEED_FACTOR : fit;
}

export function slotPreviewPlaybackRate(
  cropSpanS: number,
  targetDurationS: number,
  role: SlotRole,
): number {
  return slotRenderSpeedFactor(cropSpanS, targetDurationS, role);
}

export function formatSlotSpeedLabel(
  cropSpanS: number,
  targetDurationS: number,
  role: SlotRole,
): string {
  const fit = slotTimestretch(cropSpanS, targetDurationS);
  const epsilon = 0.02;

  let fitLabel: string;
  if (Math.abs(fit - 1) <= epsilon) {
    fitLabel = "real-time fit";
  } else if (fit > 1) {
    fitLabel = `speed up ${fit.toFixed(2)}× to fit`;
  } else {
    fitLabel = `slow down ${fit.toFixed(2)}× to fit`;
  }

  if (role === "punch") {
    return `${fitLabel} · punch slow-mo in render`;
  }
  return fitLabel;
}
