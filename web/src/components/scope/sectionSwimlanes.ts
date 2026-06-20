import type { MusicSection } from "../../types";
import { SECTION_FILLS, SCOPE_PAD_X } from "./scopeTheme";
import { timeToX, type ScopeWindow } from "./scopeWindow";

export const SECTION_LANE_HEIGHT = 14;
export const SECTION_LANE_GAP = 2;
export const SECTION_RIBBON_PAD = 2;

export interface SectionSwimlaneSegment {
  section: MusicSection;
  index: number;
  x: number;
  w: number;
  lane: number;
  fill: string;
  label: string;
}

export interface SectionSwimlaneLayout {
  segments: SectionSwimlaneSegment[];
  laneCount: number;
  height: number;
}

export function measureSectionRibbonHeight(laneCount: number): number {
  if (laneCount <= 0) {
    return 0;
  }
  return (
    SECTION_RIBBON_PAD * 2 +
    laneCount * SECTION_LANE_HEIGHT +
    Math.max(0, laneCount - 1) * SECTION_LANE_GAP
  );
}

function sectionLabelText(label: string, widthPx: number): string {
  const available = widthPx - 8;
  if (available < 14) {
    return "";
  }
  const upper = label.toUpperCase();
  const maxChars = Math.floor(available / 5);
  if (maxChars < 2) {
    return "";
  }
  if (upper.length <= maxChars) {
    return upper;
  }
  return `${upper.slice(0, maxChars - 1)}…`;
}

export function layoutSectionSwimlanes(
  sections: MusicSection[],
  window: ScopeWindow,
  viewWidth: number,
): SectionSwimlaneLayout {
  const durationS = window.endS - window.startS;
  if (durationS <= 0 || sections.length === 0) {
    return { segments: [], laneCount: 0, height: 0 };
  }

  const innerW = viewWidth - SCOPE_PAD_X * 2;
  const visible = sections
    .map((section, index) => {
      if (section.end_s <= window.startS || section.start_s >= window.endS) {
        return null;
      }
      const localStart = Math.max(section.start_s, window.startS) - window.startS;
      const localEnd = Math.min(section.end_s, window.endS) - window.startS;
      if (localEnd <= localStart + 0.001) {
        return null;
      }
      return { section, index, localStart, localEnd };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry != null)
    .sort(
      (left, right) =>
        left.localStart - right.localStart ||
        left.localEnd - right.localEnd ||
        left.index - right.index,
    );

  const laneEnds: number[] = [];
  const segments: SectionSwimlaneSegment[] = [];

  for (const entry of visible) {
    let lane = 0;
    while (lane < laneEnds.length && entry.localStart < laneEnds[lane]! - 0.001) {
      lane += 1;
    }
    if (lane === laneEnds.length) {
      laneEnds.push(entry.localEnd);
    } else {
      laneEnds[lane] = Math.max(laneEnds[lane]!, entry.localEnd);
    }

    const x = timeToX(entry.localStart, durationS, SCOPE_PAD_X, innerW);
    const xEnd = timeToX(entry.localEnd, durationS, SCOPE_PAD_X, innerW);
    const w = Math.max(2, xEnd - x);

    segments.push({
      section: entry.section,
      index: entry.index,
      x,
      w,
      lane,
      fill: SECTION_FILLS[entry.index % SECTION_FILLS.length] ?? SECTION_FILLS[0]!,
      label: sectionLabelText(entry.section.label, w),
    });
  }

  const laneCount = laneEnds.length;
  return {
    segments,
    laneCount,
    height: measureSectionRibbonHeight(laneCount),
  };
}

export function laneTopY(baseY: number, lane: number): number {
  return baseY + SECTION_RIBBON_PAD + lane * (SECTION_LANE_HEIGHT + SECTION_LANE_GAP);
}
