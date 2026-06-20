import type { MusicSection } from "../../types";
import { SECTION_FILLS, SCOPE_PAD_X } from "./scopeTheme";
import {
  formatSectionRibbonDetail,
  laneHeightForLineCount,
  SECTION_MIN_LANE_HEIGHT,
  wrapRibbonLabel,
} from "./sectionLabels";
import { timeToX, type ScopeWindow } from "./scopeWindow";

export const SECTION_LANE_HEIGHT = SECTION_MIN_LANE_HEIGHT;
export const SECTION_LANE_GAP = 2;
export const SECTION_RIBBON_PAD = 2;

export interface SectionSwimlaneSegment {
  section: MusicSection;
  index: number;
  x: number;
  w: number;
  lane: number;
  fill: string;
  labelLines: string[];
}

export interface SectionSwimlaneLayout {
  segments: SectionSwimlaneSegment[];
  laneCount: number;
  laneHeights: number[];
  height: number;
}

export function measureSectionRibbonHeight(laneHeights: number[]): number {
  if (laneHeights.length === 0) {
    return 0;
  }
  return (
    SECTION_RIBBON_PAD * 2 +
    laneHeights.reduce((total, laneHeight) => total + laneHeight, 0) +
    Math.max(0, laneHeights.length - 1) * SECTION_LANE_GAP
  );
}

export function laneTopY(
  baseY: number,
  lane: number,
  laneHeights: number[],
): number {
  let offset = SECTION_RIBBON_PAD;
  for (let index = 0; index < lane; index += 1) {
    offset += (laneHeights[index] ?? SECTION_MIN_LANE_HEIGHT) + SECTION_LANE_GAP;
  }
  return baseY + offset;
}

export function layoutSectionSwimlanes(
  sections: MusicSection[],
  window: ScopeWindow,
  viewWidth: number,
): SectionSwimlaneLayout {
  const durationS = window.endS - window.startS;
  if (durationS <= 0 || sections.length === 0) {
    return { segments: [], laneCount: 0, laneHeights: [], height: 0 };
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
      labelLines: wrapRibbonLabel(formatSectionRibbonDetail(entry.section), w),
    });
  }

  const laneCount = laneEnds.length;
  const maxLinesPerLane = Array.from({ length: laneCount }, () => 0);
  for (const segment of segments) {
    maxLinesPerLane[segment.lane] = Math.max(
      maxLinesPerLane[segment.lane] ?? 0,
      segment.labelLines.length,
    );
  }

  const laneHeights = maxLinesPerLane.map((lineCount) =>
    laneHeightForLineCount(lineCount),
  );

  return {
    segments,
    laneCount,
    laneHeights,
    height: measureSectionRibbonHeight(laneHeights),
  };
}
