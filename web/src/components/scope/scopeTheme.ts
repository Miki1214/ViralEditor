export const SCOPE_PAD_X = 4;
export const SCOPE_RULER_HEIGHT = 22;
export const SCOPE_MARKER_STRIP_HEIGHT = 28;
export const SCOPE_SECTION_RIBBON_HEIGHT = 14;
export const SCOPE_LANE_HEIGHT = 36;
export const SCOPE_CHROMA_HEADER = 16;
export const SCOPE_CHROMA_HEIGHT = 140;
export const SCOPE_GUTTER_WIDTH = 56;

export const TRACE = "#3DDC84";
export const DROP = "#F4C430";
export const BASS = "#38BDF8";
export const MUTED = "#8B9298";
export const DOWNBEAT = "rgba(139,146,152,0.55)";
export const TICK_COLOR = "rgba(139,146,152,0.35)";
export const LABEL_COLOR = "#8B9298";
export const MONITOR_BG = "#141618";
export const RULER_BG = "#101214";
export const MARKER_STRIP_BG = "#0C0E10";

export const SECTION_FILLS = [
  "rgba(56,189,248,0.22)",
  "rgba(61,220,132,0.22)",
  "rgba(244,196,48,0.22)",
  "rgba(167,139,250,0.22)",
  "rgba(248,113,113,0.22)",
  "rgba(45,212,191,0.22)",
];

export const LANE_COLORS: Record<string, string> = {
  rms: "rgba(232,234,237,0.85)",
  band_low: BASS,
  band_mid: TRACE,
  band_high: DROP,
  surge: "rgba(251,146,60,0.95)",
  vocal: "rgba(248,113,113,0.9)",
};

export const TICK_INTERVALS_S = [1, 2, 5, 10, 15, 30, 60, 120, 300];

export function formatScopeTime(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

export function timeTickInterval(durationS: number, innerW: number): number {
  if (durationS <= 0 || innerW <= 0) return 10;
  const targetSpacingPx = 96;
  const roughInterval = (durationS / innerW) * targetSpacingPx;
  for (const interval of TICK_INTERVALS_S) {
    if (interval >= roughInterval) return interval;
  }
  return TICK_INTERVALS_S[TICK_INTERVALS_S.length - 1] ?? 60;
}

export function buildTimeTicks(durationS: number, innerW: number): number[] {
  if (durationS <= 0) return [0];
  const interval = timeTickInterval(durationS, innerW);
  const ticks: number[] = [];
  for (let timeS = 0; timeS <= durationS + 0.001; timeS += interval) {
    ticks.push(Math.min(timeS, durationS));
  }
  const last = ticks[ticks.length - 1];
  if (last == null || Math.abs(last - durationS) > 0.5) {
    ticks.push(durationS);
  }
  return ticks;
}
