import { useMemo } from "react";
import type { MusicSection } from "../../types";
import { LABEL_COLOR, TICK_COLOR } from "./scopeTheme";
import {
  laneTopY,
  layoutSectionSwimlanes,
  SECTION_LANE_HEIGHT,
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
      {layout.segments.map(({ section, x, w, lane, fill, label }) => {
        const laneY = laneTopY(y, lane);
        const xEnd = x + w;
        return (
          <g key={section.id}>
            <rect
              x={x}
              y={laneY}
              width={w}
              height={SECTION_LANE_HEIGHT}
              fill={fill}
              stroke={TICK_COLOR}
              strokeWidth={0.5}
            >
              <title>
                {section.label} ({section.start_s.toFixed(1)}s–{section.end_s.toFixed(1)}s)
              </title>
            </rect>
            <line
              x1={x}
              x2={x}
              y1={laneY - 1}
              y2={laneY + SECTION_LANE_HEIGHT + 1}
              stroke={MARKER_STROKE}
              strokeWidth={1.25}
            />
            <line
              x1={xEnd}
              x2={xEnd}
              y1={laneY - 1}
              y2={laneY + SECTION_LANE_HEIGHT + 1}
              stroke={MARKER_STROKE}
              strokeWidth={1.25}
            />
            {label && (
              <text
                x={x + 4}
                y={laneY + SECTION_LANE_HEIGHT - 4}
                fill={LABEL_COLOR}
                fontSize={8}
                fontFamily="JetBrains Mono, ui-monospace, monospace"
              >
                {label}
              </text>
            )}
          </g>
        );
      })}
    </g>
  );
}

export { layoutSectionSwimlanes, type SectionSwimlaneLayout };
