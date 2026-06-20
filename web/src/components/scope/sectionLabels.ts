import type { MusicSection } from "../../types";
import { formatScopeTime } from "./scopeTheme";

export const SECTION_RIBBON_LABEL_FONT_SIZE = 7;
export const SECTION_RIBBON_LABEL_LINE_HEIGHT = 9;
export const SECTION_RIBBON_LABEL_PAD_X = 4;
export const SECTION_RIBBON_LABEL_PAD_Y = 2;
export const SECTION_RIBBON_CHAR_WIDTH = 4.25;
export const SECTION_RIBBON_MAX_LABEL_LINES = 3;
export const SECTION_MIN_LANE_HEIGHT = 14;

function formatDurationShort(durationS: number): string {
  if (durationS >= 60) {
    return formatScopeTime(durationS);
  }
  return `${Math.max(1, Math.round(durationS))}s`;
}

function sectionKind(label: string): string {
  if (label.startsWith("Hook")) return "Hook";
  if (label.startsWith("Repeated")) return "Repeated";
  if (label.startsWith("Peak")) return "Peak";
  if (label.startsWith("Section")) return "Section";
  if (label === "Full track") return "Full track";
  return label.split(" · ")[0] ?? label;
}

function energyLabel(energy: number): string {
  if (energy >= 0.65) return "loud";
  if (energy >= 0.4) return "mid";
  return "quiet";
}

/** Compact ribbon text built from section analysis fields. */
export function formatSectionRibbonDetail(section: MusicSection): string {
  if (section.label.includes(" · ")) {
    return section.label;
  }

  const durationS = Math.max(0, section.end_s - section.start_s);
  const parts = [sectionKind(section.label), formatDurationShort(durationS)];

  if (section.drop_count > 0) {
    parts.push(`${section.drop_count} drop${section.drop_count === 1 ? "" : "s"}`);
  }
  parts.push(energyLabel(section.energy));
  if (section.repetition_count > 1) {
    parts.push(`×${section.repetition_count} in track`);
  }

  return parts.join(" · ");
}

export function formatSectionTooltip(section: MusicSection): string {
  const durationS = Math.max(0, section.end_s - section.start_s);
  const detail = formatSectionRibbonDetail(section);
  const energyPct = Math.round(section.energy * 100);
  return `${detail} — ${formatScopeTime(section.start_s)}–${formatScopeTime(section.end_s)} (${formatDurationShort(durationS)}) · energy ${energyPct}%`;
}

export function maxCharsForRibbonWidth(widthPx: number): number {
  const innerW = widthPx - SECTION_RIBBON_LABEL_PAD_X * 2;
  if (innerW < 16) {
    return 0;
  }
  return Math.max(4, Math.floor(innerW / SECTION_RIBBON_CHAR_WIDTH));
}

/** Wrap label parts onto multiple lines that fit the segment width. */
export function wrapRibbonLabel(
  text: string,
  widthPx: number,
  maxLines: number = SECTION_RIBBON_MAX_LABEL_LINES,
): string[] {
  const maxChars = maxCharsForRibbonWidth(widthPx);
  if (maxChars <= 0) {
    return [];
  }

  const parts = text.split(" · ");
  const lines: string[] = [];
  let current = "";

  const flushCurrent = () => {
    if (!current) {
      return;
    }
    lines.push(current);
    current = "";
  };

  for (const part of parts) {
    const candidate = current ? `${current} · ${part}` : part;
    if (candidate.length <= maxChars) {
      current = candidate;
      continue;
    }

    flushCurrent();
    if (part.length <= maxChars) {
      current = part;
      continue;
    }

    let rest = part;
    while (rest.length > maxChars && lines.length < maxLines - 1) {
      lines.push(rest.slice(0, maxChars));
      rest = rest.slice(maxChars);
    }
    if (lines.length >= maxLines) {
      break;
    }
    current =
      rest.length > maxChars ? `${rest.slice(0, maxChars - 1)}…` : rest;
  }

  flushCurrent();

  if (lines.length > maxLines) {
    const trimmed = lines.slice(0, maxLines);
    const last = trimmed[maxLines - 1]!;
    trimmed[maxLines - 1] =
      last.length > maxChars ? `${last.slice(0, maxChars - 1)}…` : last;
    return trimmed;
  }

  if (lines.length === maxLines) {
    const last = lines[maxLines - 1]!;
    if (last.length > maxChars) {
      lines[maxLines - 1] = `${last.slice(0, maxChars - 1)}…`;
    }
  }

  return lines;
}

export function laneHeightForLineCount(lineCount: number): number {
  if (lineCount <= 0) {
    return SECTION_MIN_LANE_HEIGHT;
  }
  return (
    SECTION_RIBBON_LABEL_PAD_Y * 2 + lineCount * SECTION_RIBBON_LABEL_LINE_HEIGHT
  );
}
