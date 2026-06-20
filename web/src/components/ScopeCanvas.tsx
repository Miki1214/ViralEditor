import { useMemo } from "react";
import type { MusicBlock, MusicSection, Transient, WaveformPoint } from "../types";
import { resamplePointsToPixelWidth } from "./scope/scopePoints";
import { scopeWidth } from "./scope/scopeLayout";
import { ScopeMarkerStrip } from "./scope/ScopeMarkerStrip";
import { SectionRibbon } from "./scope/SectionRibbon";
import {
  buildTimeTicks,
  DROP,
  formatScopeTime,
  LABEL_COLOR,
  RULER_BG,
  SCOPE_MARKER_STRIP_HEIGHT,
  SCOPE_PAD_X,
  SCOPE_RULER_HEIGHT,
  SCOPE_SECTION_RIBBON_HEIGHT,
  TICK_COLOR,
  TRACE,
} from "./scope/scopeTheme";
import { cropTimesToWindow, timeToX, type ScopeWindow } from "./scope/scopeWindow";

interface ScopeCanvasProps {
  durationS: number;
  points: WaveformPoint[];
  transients: Transient[];
  sections: MusicSection[];
  beats: number[];
  downbeats: number[];
  blocks: MusicBlock[];
  selectedBlockId: string | null;
  playingBlockId: string | null;
  window?: ScopeWindow;
}

const WAVEFORM_HEIGHT = 140;
const TOTAL_HEIGHT =
  SCOPE_SECTION_RIBBON_HEIGHT +
  WAVEFORM_HEIGHT +
  SCOPE_RULER_HEIGHT +
  SCOPE_MARKER_STRIP_HEIGHT;

export function ScopeCanvas({
  durationS,
  points,
  transients,
  sections,
  downbeats,
  blocks,
  selectedBlockId,
  playingBlockId,
  window,
}: ScopeCanvasProps) {
  const scopeWindow: ScopeWindow = window ?? { startS: 0, endS: durationS };
  const windowDurationS = Math.max(scopeWindow.endS - scopeWindow.startS, durationS);
  const width = scopeWidth(windowDurationS);
  const padX = SCOPE_PAD_X;
  const padY = 10;
  const waveformTop = SCOPE_SECTION_RIBBON_HEIGHT;
  const innerW = width - padX * 2;
  const innerH = WAVEFORM_HEIGHT - padY * 2;
  const rulerTop = waveformTop + WAVEFORM_HEIGHT;
  const markerStripTop = rulerTop + SCOPE_RULER_HEIGHT;

  const localPoints = useMemo(() => {
    if (!window || (window.startS === 0 && window.endS === durationS)) {
      return points.map((point) => ({ t: point.t, v: point.v }));
    }
    return points
      .filter((point) => point.t >= window.startS - 0.001 && point.t <= window.endS + 0.001)
      .map((point) => ({ t: point.t - window.startS, v: point.v }));
  }, [points, window, durationS]);

  const localDownbeats = useMemo(
    () => cropTimesToWindow(downbeats, scopeWindow),
    [downbeats, scopeWindow],
  );

  const displayPoints = useMemo(
    () => resamplePointsToPixelWidth(localPoints, innerW),
    [localPoints, innerW],
  );

  const path = useMemo(() => {
    if (displayPoints.length === 0 || windowDurationS <= 0) return "";
    return displayPoints
      .map((point, index) => {
        const x = padX + (point.t / windowDurationS) * innerW;
        const y = waveformTop + padY + innerH - point.v * innerH;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
  }, [displayPoints, windowDurationS, innerW, innerH, padX, padY, waveformTop]);

  const accentCandidates = useMemo(
    () =>
      transients.filter(
        (transient) => transient.type === "drop" || transient.type === "bass",
      ),
    [transients],
  );

  const timeTicks = useMemo(
    () => buildTimeTicks(windowDurationS, innerW),
    [windowDurationS, innerW],
  );

  const activeId = playingBlockId ?? selectedBlockId;

  return (
    <svg
      viewBox={`0 0 ${width} ${TOTAL_HEIGHT}`}
      width={width}
      height={TOTAL_HEIGHT}
      className="block max-w-none bg-[#141618]"
      role="img"
      aria-label="Audio scope waveform"
    >
      <SectionRibbon sections={sections} window={scopeWindow} viewWidth={width} y={0} />

      {blocks.map((block) => {
        if (block.end_s <= scopeWindow.startS || block.start_s >= scopeWindow.endS) return null;
        const localStart = Math.max(block.start_s, scopeWindow.startS) - scopeWindow.startS;
        const localEnd = Math.min(block.end_s, scopeWindow.endS) - scopeWindow.startS;
        const x = padX + (localStart / windowDurationS) * innerW;
        const w = Math.max(2, ((localEnd - localStart) / windowDurationS) * innerW);
        const selected = block.id === activeId;
        return (
          <rect
            key={block.id}
            x={x}
            y={waveformTop + padY}
            width={w}
            height={innerH}
            fill={selected ? "rgba(244,196,48,0.22)" : "rgba(244,196,48,0.08)"}
            stroke={selected ? DROP : "rgba(244,196,48,0.35)"}
            strokeWidth={selected ? 1.5 : 1}
            rx={2}
          />
        );
      })}

      {path && (
        <path
          d={path}
          fill="none"
          stroke={TRACE}
          strokeWidth={1.75}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}

      <rect x={0} y={rulerTop} width={width} height={SCOPE_RULER_HEIGHT} fill={RULER_BG} />
      <line
        x1={padX}
        x2={width - padX}
        y1={rulerTop}
        y2={rulerTop}
        stroke={TICK_COLOR}
        strokeWidth={1}
      />

      {timeTicks.map((timeS) => {
        const x = timeToX(timeS, windowDurationS, padX, innerW);
        const anchor = timeS <= 0 ? "start" : timeS >= windowDurationS - 0.5 ? "end" : "middle";
        return (
          <g key={`tick-${timeS}`}>
            <line
              x1={x}
              x2={x}
              y1={rulerTop + 2}
              y2={rulerTop + 8}
              stroke={TICK_COLOR}
              strokeWidth={1}
            />
            <text
              x={x}
              y={rulerTop + SCOPE_RULER_HEIGHT - 6}
              fill={LABEL_COLOR}
              fontSize={10}
              fontFamily="ui-monospace, SFMono-Regular, Menlo, monospace"
              textAnchor={anchor}
            >
              {formatScopeTime(timeS)}
            </text>
          </g>
        );
      })}

      <ScopeMarkerStrip
        window={{ startS: 0, endS: windowDurationS }}
        viewWidth={width}
        y={markerStripTop}
        height={SCOPE_MARKER_STRIP_HEIGHT}
        downbeats={localDownbeats}
        accents={accentCandidates}
      />
    </svg>
  );
}

function blockPixelRange(
  durationS: number,
  startS: number,
  endS: number,
): { startX: number; endX: number; canvasWidth: number } {
  const canvasWidth = scopeWidth(durationS);
  const innerW = canvasWidth - SCOPE_PAD_X * 2;
  return {
    startX: SCOPE_PAD_X + (startS / durationS) * innerW,
    endX: SCOPE_PAD_X + (endS / durationS) * innerW,
    canvasWidth,
  };
}

export { blockPixelRange, scopeWidth, WAVEFORM_HEIGHT as SCOPE_HEIGHT };
