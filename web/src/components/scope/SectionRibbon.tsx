import { useMemo } from "react";
import type { MusicSection } from "../../types";
import { LABEL_COLOR, TICK_COLOR } from "./scopeTheme";
import {
  formatSectionTooltip,
  SECTION_RIBBON_LABEL_FONT_SIZE,
  SECTION_RIBBON_LABEL_LINE_HEIGHT,
  SECTION_RIBBON_LABEL_PAD_X,
  SECTION_RIBBON_LABEL_PAD_Y,
} from "./sectionLabels";
import {
  laneTopY,
  layoutSectionSwimlanes,
  type SectionSwimlaneLayout,
} from "./sectionSwimlanes";
import type { ScopeWindow } from "./scopeWindow";

interface SectionRibbonProps {
  sections: MusicSection[];
  window: ScopeWindow;
  viewWidth: number;
  y?: number;
  layout?: SectionSwimlaneLayout;
}

const MARKER_STROKE = "rgba(232,234,237,0.55)";

function SectionLabel({
  clipId,
  x,
  laneY,
  width,
  laneHeight,
  lines,
}: {
  clipId: string;
  x: number;
  laneY: number;
  width: number;
  laneHeight: number;
  lines: string[];
}) {
  if (lines.length === 0) {
    return null;
  }

  const textX = x + SECTION_RIBBON_LABEL_PAD_X;

  return (
    <>
      <clipPath id={clipId}>
        <rect x={x} y={laneY} width={width} height={laneHeight} />
      </clipPath>
      <text
        clipPath={`url(#${clipId})`}
        x={textX}
        y={laneY + SECTION_RIBBON_LABEL_PAD_Y}
        fill={LABEL_COLOR}
        fontSize={SECTION_RIBBON_LABEL_FONT_SIZE}
        fontFamily="JetBrains Mono, ui-monospace, monospace"
        dominantBaseline="hanging"
      >
        {lines.map((line, lineIndex) => (
          <tspan
            key={`${clipId}-${lineIndex}`}
            x={textX}
            dy={lineIndex === 0 ? 0 : SECTION_RIBBON_LABEL_LINE_HEIGHT}
          >
            {line}
          </tspan>
        ))}
      </text>
    </>
  );
}

export function SectionRibbon({
  sections,
  window,
  viewWidth,
  y = 0,
  layout: layoutProp,
}: SectionRibbonProps) {
  const layout = useMemo(
    () => layoutProp ?? layoutSectionSwimlanes(sections, window, viewWidth),
    [layoutProp, sections, window, viewWidth],
  );

  if (layout.height <= 0 || layout.segments.length === 0) {
    return null;
  }

  return (
    <g aria-hidden>
      <rect x={0} y={y} width={viewWidth} height={layout.height} fill="#0d0f10" />
      {layout.segments.map(({ section, index, x, w, lane, fill, labelLines }) => {
        const laneY = laneTopY(y, lane, layout.laneHeights);
        const laneHeight = layout.laneHeights[lane] ?? SECTION_RIBBON_LABEL_PAD_Y * 2;
        const xEnd = x + w;
        const clipId = `section-label-${section.id}-${index}`;

        return (
          <g key={`${section.id}-${index}`}>
            <rect
              x={x}
              y={laneY}
              width={w}
              height={laneHeight}
              fill={fill}
              stroke={TICK_COLOR}
              strokeWidth={0.5}
            >
              <title>{formatSectionTooltip(section)}</title>
            </rect>
            <line
              x1={x}
              x2={x}
              y1={laneY - 1}
              y2={laneY + laneHeight + 1}
              stroke={MARKER_STROKE}
              strokeWidth={1.25}
            />
            <line
              x1={xEnd}
              x2={xEnd}
              y1={laneY - 1}
              y2={laneY + laneHeight + 1}
              stroke={MARKER_STROKE}
              strokeWidth={1.25}
            />
            <SectionLabel
              clipId={clipId}
              x={x}
              laneY={laneY}
              width={w}
              laneHeight={laneHeight}
              lines={labelLines}
            />
          </g>
        );
      })}
    </g>
  );
}

export { layoutSectionSwimlanes, type SectionSwimlaneLayout };
