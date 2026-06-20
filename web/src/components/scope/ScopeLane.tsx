import { useMemo } from "react";
import type { WaveformPoint } from "../../types";
import { resamplePointsToPixelWidth } from "./scopePoints";
import { LANE_COLORS, LABEL_COLOR, SCOPE_GUTTER_WIDTH, SCOPE_PAD_X } from "./scopeTheme";
import { timeToX, type ScopeWindow } from "./scopeWindow";

interface ScopeLaneProps {
  laneId: string;
  label: string;
  points: WaveformPoint[];
  window: ScopeWindow;
  viewWidth: number;
  height: number;
  y: number;
  playheadS?: number | null;
  hoverS?: number | null;
}

export function ScopeLane({
  laneId,
  label,
  points,
  window,
  viewWidth,
  height,
  y,
  playheadS = null,
  hoverS = null,
}: ScopeLaneProps) {
  const durationS = window.endS - window.startS;
  const plotX = SCOPE_GUTTER_WIDTH;
  const innerW = viewWidth - plotX - SCOPE_PAD_X;
  const padY = 4;
  const innerH = height - padY * 2;
  const stroke = LANE_COLORS[laneId] ?? "#3DDC84";

  const displayPoints = useMemo(
    () => resamplePointsToPixelWidth(points, innerW),
    [points, innerW],
  );

  const path = useMemo(() => {
    if (displayPoints.length === 0 || durationS <= 0) return "";
    return displayPoints
      .map((point, index) => {
        const x = timeToX(point.t, durationS, plotX, innerW);
        const laneY = y + padY + innerH - point.v * innerH;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${laneY.toFixed(2)}`;
      })
      .join(" ");
  }, [displayPoints, durationS, plotX, innerW, y, padY, innerH]);

  const areaPath = useMemo(() => {
    if (!path || durationS <= 0) return "";
    const baseline = y + padY + innerH;
    const startX = timeToX(displayPoints[0]?.t ?? 0, durationS, plotX, innerW);
    const endX = timeToX(displayPoints[displayPoints.length - 1]?.t ?? durationS, durationS, plotX, innerW);
    return `${path} L ${endX.toFixed(2)} ${baseline.toFixed(2)} L ${startX.toFixed(2)} ${baseline.toFixed(2)} Z`;
  }, [path, displayPoints, durationS, plotX, innerW, y, padY, innerH]);

  const renderCrosshair = (timeS: number, key: string, opacity: number) => {
    const x = timeToX(timeS, durationS, plotX, innerW);
    return (
      <line
        key={key}
        x1={x}
        x2={x}
        y1={y + 1}
        y2={y + height - 1}
        stroke="#E8EAED"
        strokeWidth={1}
        opacity={opacity}
      />
    );
  };

  return (
    <g aria-label={`${label} lane`}>
      <rect x={0} y={y} width={viewWidth} height={height} fill="#121416" />
      <line x1={0} x2={viewWidth} y1={y} y2={y} stroke="rgba(139,146,152,0.12)" strokeWidth={1} />
      <text
        x={8}
        y={y + height / 2 + 4}
        fill={LABEL_COLOR}
        fontSize={9}
        fontFamily="JetBrains Mono, ui-monospace, monospace"
        letterSpacing="0.04em"
      >
        {label.toUpperCase()}
      </text>
      {areaPath && (
        <path d={areaPath} fill={stroke} opacity={0.12} style={{ pointerEvents: "none" }} />
      )}
      {path && (
        <path
          d={path}
          fill="none"
          stroke={stroke}
          strokeWidth={1.25}
          strokeLinejoin="round"
          strokeLinecap="round"
          style={{ pointerEvents: "none" }}
        />
      )}
      {playheadS != null && playheadS >= 0 && renderCrosshair(playheadS, "playhead", 0.9)}
      {hoverS != null && hoverS >= 0 && renderCrosshair(hoverS, "hover", 0.35)}
    </g>
  );
}
