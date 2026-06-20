import { useMemo } from "react";
import type { ChromaGram } from "../../types";
import {
  DROP,
  LABEL_COLOR,
  SCOPE_CHROMA_HEADER,
  SCOPE_CHROMA_HEIGHT,
  SCOPE_GUTTER_WIDTH,
  SCOPE_PAD_X,
} from "./scopeTheme";
import { timeToX, type ScopeWindow } from "./scopeWindow";

interface ChromaHeatmapProps {
  chroma: ChromaGram;
  window: ScopeWindow;
  viewWidth: number;
  y: number;
  height?: number;
  playheadS?: number | null;
  hoverS?: number | null;
}

const PITCH_FONT = 10;
const HEADER_FONT = 9;

function chromaFill(value: number): string {
  const clamped = Math.max(0, Math.min(1, value));
  const alpha = 0.08 + clamped * 0.82;
  return `rgba(61,220,132,${alpha.toFixed(3)})`;
}

export function ChromaHeatmap({
  chroma,
  window,
  viewWidth,
  y,
  height = SCOPE_CHROMA_HEIGHT,
  playheadS = null,
  hoverS = null,
}: ChromaHeatmapProps) {
  const durationS = window.endS - window.startS;
  const plotX = SCOPE_GUTTER_WIDTH;
  const innerW = viewWidth - plotX - SCOPE_PAD_X;
  const gridTop = y + SCOPE_CHROMA_HEADER;
  const gridH = height - SCOPE_CHROMA_HEADER - 2;
  const rowCount = Math.max(chroma.pitch_classes.length, 1);
  const rowH = gridH / rowCount;

  const cells = useMemo(() => {
    if (durationS <= 0 || chroma.frames.length === 0) return [];
    const items: Array<{
      key: string;
      x: number;
      cellY: number;
      w: number;
      h: number;
      fill: string;
    }> = [];

    for (let frameIndex = 0; frameIndex < chroma.frames.length; frameIndex += 1) {
      const timeS = chroma.times[frameIndex] ?? 0;
      const nextTimeS = chroma.times[frameIndex + 1] ?? durationS;
      const x = timeToX(timeS, durationS, plotX, innerW);
      const nextX = timeToX(nextTimeS, durationS, plotX, innerW);
      const w = Math.max(1, nextX - x);
      const frame = chroma.frames[frameIndex] ?? [];
      for (let pitchIndex = 0; pitchIndex < chroma.pitch_classes.length; pitchIndex += 1) {
        const value = frame[pitchIndex] ?? 0;
        items.push({
          key: `${frameIndex}-${pitchIndex}`,
          x,
          cellY: gridTop + pitchIndex * rowH,
          w,
          h: Math.max(1, rowH - 1),
          fill: chromaFill(value),
        });
      }
    }
    return items;
  }, [chroma, durationS, plotX, innerW, gridTop, rowH]);

  const renderCrosshair = (timeS: number, key: string, opacity: number) => {
    const x = timeToX(timeS, durationS, plotX, innerW);
    return (
      <line
        key={key}
        x1={x}
        x2={x}
        y1={gridTop}
        y2={y + height - 1}
        stroke="#E8EAED"
        strokeWidth={1}
        opacity={opacity}
      />
    );
  };

  return (
    <g aria-label="Pitch-class heatmap">
      <rect x={0} y={y} width={viewWidth} height={height} fill="#121416" />
      <line x1={0} x2={viewWidth} y1={y} y2={y} stroke="rgba(139,146,152,0.12)" strokeWidth={1} />
      <rect x={0} y={y} width={SCOPE_GUTTER_WIDTH} height={SCOPE_CHROMA_HEADER} fill="#0d0f10" />
      <text
        x={8}
        y={y + 11}
        fill={LABEL_COLOR}
        fontSize={HEADER_FONT}
        fontFamily="JetBrains Mono, ui-monospace, monospace"
        letterSpacing="0.08em"
      >
        CHROMA
      </text>
      <line
        x1={SCOPE_GUTTER_WIDTH}
        x2={SCOPE_GUTTER_WIDTH}
        y1={y}
        y2={y + height}
        stroke="rgba(139,146,152,0.12)"
        strokeWidth={1}
      />
      {chroma.pitch_classes.map((pitch, index) => {
        const isTonic = chroma.tonic != null && pitch === chroma.tonic;
        const rowCenterY = gridTop + index * rowH + rowH / 2;
        return (
          <text
            key={pitch}
            x={SCOPE_GUTTER_WIDTH - 8}
            y={rowCenterY + 3.5}
            fill={isTonic ? DROP : LABEL_COLOR}
            fontSize={PITCH_FONT}
            fontWeight={isTonic ? 600 : 400}
            fontFamily="JetBrains Mono, ui-monospace, monospace"
            textAnchor="end"
          >
            {pitch}
          </text>
        );
      })}
      {cells.map((cell) => (
        <rect
          key={cell.key}
          x={cell.x}
          y={cell.cellY}
          width={cell.w}
          height={cell.h}
          fill={cell.fill}
        />
      ))}
      {playheadS != null && playheadS >= 0 && renderCrosshair(playheadS, "playhead", 0.9)}
      {hoverS != null && hoverS >= 0 && renderCrosshair(hoverS, "hover", 0.35)}
    </g>
  );
}
