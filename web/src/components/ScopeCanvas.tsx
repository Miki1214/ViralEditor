import { useMemo } from "react";
import type { MusicBlock, MusicSection, Transient, WaveformPoint } from "../types";
import { ScopeBeatGrid } from "./scope/ScopeBeatGrid";
import { SectionRibbon } from "./scope/SectionRibbon";
import {
  buildTimeTicks,
  DROP,
  formatScopeTime,
  LABEL_COLOR,
  RULER_BG,
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

const BASS = "#38BDF8";
const MUTED = "#8B9298";

const WAVEFORM_HEIGHT = 140;
const TOTAL_HEIGHT = SCOPE_SECTION_RIBBON_HEIGHT + WAVEFORM_HEIGHT + SCOPE_RULER_HEIGHT;
const MIN_SCOPE_WIDTH = 960;
const PIXELS_PER_SECOND = 8;
const LONG_TRACK_S = 90;

function transientColor(type: Transient["type"]): string {
  if (type === "drop") return DROP;
  if (type === "bass") return BASS;
  return MUTED;
}

function scopeWidth(durationS: number): number {
  if (durationS <= 0) return MIN_SCOPE_WIDTH;
  return Math.max(MIN_SCOPE_WIDTH, Math.ceil(durationS * PIXELS_PER_SECOND));
}

function visibleTransients(transients: Transient[], durationS: number): Transient[] {
  if (durationS <= LONG_TRACK_S || transients.length <= 150) {
    return transients;
  }
  return transients.filter((transient) => transient.type !== "percussive");
}

export function ScopeCanvas({
  durationS,
  points,
  transients,
  sections,
  beats,
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

  const localPoints = useMemo(() => {
    if (!window || (window.startS === 0 && window.endS === durationS)) {
      return points.map((point) => ({ t: point.t, v: point.v }));
    }
    return points
      .filter((point) => point.t >= window.startS - 0.001 && point.t <= window.endS + 0.001)
      .map((point) => ({ t: point.t - window.startS, v: point.v }));
  }, [points, window, durationS]);

  const localBeats = useMemo(
    () => cropTimesToWindow(beats, scopeWindow),
    [beats, scopeWindow],
  );
  const localDownbeats = useMemo(
    () => cropTimesToWindow(downbeats, scopeWindow),
    [downbeats, scopeWindow],
  );

  const path = useMemo(() => {
    if (localPoints.length === 0 || windowDurationS <= 0) return "";
    return localPoints
      .map((point, index) => {
        const x = padX + (point.t / windowDurationS) * innerW;
        const y = waveformTop + padY + innerH - point.v * innerH;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
  }, [localPoints, windowDurationS, innerW, innerH, padX, padY, waveformTop]);

  const markers = useMemo(
    () => visibleTransients(transients, durationS),
    [transients, durationS],
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
      className="block max-w-none rounded border border-monitor-border bg-[#141618]"
      role="img"
      aria-label="Audio scope waveform"
    >
      <SectionRibbon sections={sections} window={scopeWindow} viewWidth={width} y={0} />

      <rect
        x={0}
        y={waveformTop + WAVEFORM_HEIGHT}
        width={width}
        height={SCOPE_RULER_HEIGHT}
        fill={RULER_BG}
      />
      <line
        x1={padX}
        x2={width - padX}
        y1={waveformTop + WAVEFORM_HEIGHT}
        y2={waveformTop + WAVEFORM_HEIGHT}
        stroke={TICK_COLOR}
        strokeWidth={1}
      />

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

      <ScopeBeatGrid
        beats={localBeats}
        downbeats={localDownbeats}
        window={{ startS: 0, endS: windowDurationS }}
        viewWidth={width}
        topY={waveformTop + padY}
        bottomY={waveformTop + WAVEFORM_HEIGHT - padY}
      />

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

      {markers.map((transient) => {
        const timeS = transient.timestamp_ms / 1000;
        if (timeS < scopeWindow.startS - 0.001 || timeS > scopeWindow.endS + 0.001) return null;
        const local = timeS - scopeWindow.startS;
        const x = padX + (local / windowDurationS) * innerW;
        return (
          <line
            key={`${transient.timestamp_ms}-${transient.type}`}
            x1={x}
            x2={x}
            y1={waveformTop + padY}
            y2={waveformTop + WAVEFORM_HEIGHT - padY}
            stroke={transientColor(transient.type)}
            strokeWidth={transient.type === "drop" ? 2.5 : 1}
            opacity={transient.type === "percussive" ? 0.45 : 0.9}
          />
        );
      })}

      {timeTicks.map((timeS) => {
        const x = timeToX(timeS, windowDurationS, padX, innerW);
        const anchor = timeS <= 0 ? "start" : timeS >= windowDurationS - 0.5 ? "end" : "middle";
        return (
          <g key={`tick-${timeS}`}>
            <line
              x1={x}
              x2={x}
              y1={waveformTop + WAVEFORM_HEIGHT - 4}
              y2={waveformTop + WAVEFORM_HEIGHT + 5}
              stroke={TICK_COLOR}
              strokeWidth={1}
            />
            <text
              x={x}
              y={TOTAL_HEIGHT - 5}
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
