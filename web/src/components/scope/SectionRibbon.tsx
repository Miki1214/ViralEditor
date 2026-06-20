import { useId, useMemo } from "react";
import type { MusicSection } from "../../types";
import { LABEL_COLOR, SECTION_FILLS, SCOPE_PAD_X, SCOPE_SECTION_RIBBON_HEIGHT } from "./scopeTheme";
import { timeToX, type ScopeWindow } from "./scopeWindow";

interface SectionRibbonProps {
  sections: MusicSection[];
  window: ScopeWindow;
  viewWidth: number;
  y?: number;
}

const LABEL_CHAR_W = 5;
const LABEL_PAD_X = 4;
const LABEL_GAP = 3;
/** Minimum segment width before we attempt a label. */
const MIN_SEGMENT_W = 28;

interface SectionLayout {
  section: MusicSection;
  index: number;
  x: number;
  w: number;
  text: string;
  labelX: number;
  clipId: string;
}

function sectionLabelText(label: string, widthPx: number): string | null {
  const available = widthPx - LABEL_PAD_X * 2;
  if (available < 16) return null;
  const upper = label.toUpperCase();
  const maxChars = Math.floor(available / LABEL_CHAR_W);
  if (maxChars < 2) return null;
  if (upper.length <= maxChars) return upper;
  return `${upper.slice(0, maxChars - 1)}…`;
}

function estimateTextWidth(text: string): number {
  return text.length * LABEL_CHAR_W;
}

function layoutSectionLabels(
  sections: MusicSection[],
  window: ScopeWindow,
  durationS: number,
  innerW: number,
  clipPrefix: string,
): SectionLayout[] {
  const candidates = sections
    .map((section, index) => {
      if (section.end_s <= window.startS || section.start_s >= window.endS) return null;
      const localStart = Math.max(section.start_s, window.startS) - window.startS;
      const localEnd = Math.min(section.end_s, window.endS) - window.startS;
      const x = timeToX(localStart, durationS, SCOPE_PAD_X, innerW);
      const w = Math.max(1, timeToX(localEnd, durationS, SCOPE_PAD_X, innerW) - x);
      if (w < MIN_SEGMENT_W) return null;
      const text = sectionLabelText(section.label, w);
      if (text == null) return null;
      const textW = estimateTextWidth(text);
      if (textW > w - LABEL_PAD_X * 2) return null;
      return { section, index, x, w, text, textW };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry != null)
    .sort((a, b) => a.x - b.x);

  const placed: SectionLayout[] = [];
  let occupiedUntil = -Infinity;

  for (const entry of candidates) {
    const minX = entry.x + LABEL_PAD_X;
    const maxX = entry.x + entry.w - LABEL_PAD_X - entry.textW;
    if (maxX < minX) continue;

    const labelX = Math.max(minX, occupiedUntil + LABEL_GAP);
    if (labelX > maxX) continue;

    placed.push({
      section: entry.section,
      index: entry.index,
      x: entry.x,
      w: entry.w,
      text: entry.text,
      labelX,
      clipId: `${clipPrefix}-section-label-${entry.section.id}`,
    });
    occupiedUntil = labelX + entry.textW;
  }

  return placed;
}

export function SectionRibbon({
  sections,
  window,
  viewWidth,
  y = 0,
}: SectionRibbonProps) {
  const clipPrefix = useId().replace(/:/g, "");
  const durationS = window.endS - window.startS;
  const innerW = viewWidth - SCOPE_PAD_X * 2;

  const layouts = useMemo(
    () =>
      durationS > 0 && sections.length > 0
        ? layoutSectionLabels(sections, window, durationS, innerW, clipPrefix)
        : [],
    [sections, window, durationS, innerW, clipPrefix],
  );

  if (durationS <= 0 || sections.length === 0) return null;

  const bandSections = sections
    .map((section, index) => {
      if (section.end_s <= window.startS || section.start_s >= window.endS) return null;
      const localStart = Math.max(section.start_s, window.startS) - window.startS;
      const localEnd = Math.min(section.end_s, window.endS) - window.startS;
      const x = timeToX(localStart, durationS, SCOPE_PAD_X, innerW);
      const w = Math.max(1, timeToX(localEnd, durationS, SCOPE_PAD_X, innerW) - x);
      return { section, index, x, w };
    })
    .filter((entry): entry is NonNullable<typeof entry> => entry != null);

  return (
    <g aria-hidden>
      <defs>
        {layouts.map(({ clipId, x, w }) => (
          <clipPath key={clipId} id={clipId} clipPathUnits="userSpaceOnUse">
            <rect x={x} y={y} width={w} height={SCOPE_SECTION_RIBBON_HEIGHT} />
          </clipPath>
        ))}
      </defs>
      <rect
        x={0}
        y={y}
        width={viewWidth}
        height={SCOPE_SECTION_RIBBON_HEIGHT}
        fill="#0d0f10"
      />
      {bandSections.map(({ section, index, x, w }) => (
        <g key={section.id}>
          <rect
            x={x}
            y={y}
            width={w}
            height={SCOPE_SECTION_RIBBON_HEIGHT}
            fill={SECTION_FILLS[index % SECTION_FILLS.length]}
          >
            <title>{section.label}</title>
          </rect>
        </g>
      ))}
      {layouts.map(({ section, clipId, labelX, text }) => (
        <text
          key={`label-${section.id}`}
          x={labelX}
          y={y + 10}
          fill={LABEL_COLOR}
          fontSize={8}
          fontFamily="JetBrains Mono, ui-monospace, monospace"
          clipPath={`url(#${clipId})`}
        >
          {text}
          <title>{section.label}</title>
        </text>
      ))}
    </g>
  );
}
