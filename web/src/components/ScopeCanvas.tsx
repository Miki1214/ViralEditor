import { useMemo } from "react";
import type { MusicBlock, MusicSection, Transient, WaveformPoint } from "../types";

interface ScopeCanvasProps {
  durationS: number;
  points: WaveformPoint[];
  transients: Transient[];
  sections: MusicSection[];
  downbeats: number[];
  blocks: MusicBlock[];
  selectedBlockId: string | null;
  playingBlockId: string | null;
}

const TRACE = "#3DDC84";
const DROP = "#F4C430";
const BASS = "#38BDF8";
const MUTED = "#8B9298";
const DOWNBEAT = "rgba(139,146,152,0.55)";
const TICK_COLOR = "rgba(139,146,152,0.35)";
const LABEL_COLOR = "#8B9298";

const WAVEFORM_HEIGHT = 140;
const RULER_HEIGHT = 22;
const TOTAL_HEIGHT = WAVEFORM_HEIGHT + RULER_HEIGHT;
const MIN_SCOPE_WIDTH = 960;
const PIXELS_PER_SECOND = 8;
const LONG_TRACK_S = 90;

const SECTION_FILLS = [
  "rgba(56,189,248,0.08)",
  "rgba(61,220,132,0.08)",
  "rgba(244,196,48,0.08)",
  "rgba(167,139,250,0.08)",
  "rgba(248,113,113,0.08)",
  "rgba(45,212,191,0.08)",
];

const TICK_INTERVALS_S = [1, 2, 5, 10, 15, 30, 60, 120, 300];

function transientColor(type: Transient["type"]): string {
  if (type === "drop") return DROP;
  if (type === "bass") return BASS;
  return MUTED;
}

function scopeWidth(durationS: number): number {
  if (durationS <= 0) return MIN_SCOPE_WIDTH;
  return Math.max(MIN_SCOPE_WIDTH, Math.ceil(durationS * PIXELS_PER_SECOND));
}

const SCOPE_PAD_X = 4;

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

function formatScopeTime(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(total / 60);
  const secs = total % 60;
  return `${minutes}:${secs.toString().padStart(2, "0")}`;
}

function timeTickInterval(durationS: number, innerW: number): number {
  if (durationS <= 0 || innerW <= 0) return 10;
  const targetSpacingPx = 96;
  const roughInterval = (durationS / innerW) * targetSpacingPx;
  for (const interval of TICK_INTERVALS_S) {
    if (interval >= roughInterval) return interval;
  }
  return TICK_INTERVALS_S[TICK_INTERVALS_S.length - 1];
}

function buildTimeTicks(durationS: number, innerW: number): number[] {
  if (durationS <= 0) return [0];
  const interval = timeTickInterval(durationS, innerW);
  const ticks: number[] = [];
  for (let timeS = 0; timeS <= durationS + 0.001; timeS += interval) {
    ticks.push(Math.min(timeS, durationS));
  }
  const last = ticks[ticks.length - 1];
  if (last == null || Math.abs(last - durationS) > 0.5) {
    ticks.push(durationS);
  }
  return ticks;
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
  downbeats,
  blocks,
  selectedBlockId,
  playingBlockId,
}: ScopeCanvasProps) {
  const width = scopeWidth(durationS);
  const padX = 4;
  const padY = 10;
  const innerW = width - padX * 2;
  const innerH = WAVEFORM_HEIGHT - padY * 2;

  const path = useMemo(() => {
    if (points.length === 0 || durationS <= 0) return "";
    return points
      .map((point, index) => {
        const x = padX + (point.t / durationS) * innerW;
        const y = padY + innerH - point.v * innerH;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
  }, [points, durationS, innerW, innerH, padX, padY]);

  const markers = useMemo(
    () => visibleTransients(transients, durationS),
    [transients, durationS],
  );

  const timeTicks = useMemo(
    () => buildTimeTicks(durationS, innerW),
    [durationS, innerW],
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
      <rect
        x={0}
        y={WAVEFORM_HEIGHT}
        width={width}
        height={RULER_HEIGHT}
        fill="#101214"
      />
      <line
        x1={padX}
        x2={width - padX}
        y1={WAVEFORM_HEIGHT}
        y2={WAVEFORM_HEIGHT}
        stroke={TICK_COLOR}
        strokeWidth={1}
      />

      {sections.map((section, index) => {
        const x = padX + (section.start_s / durationS) * innerW;
        const w = Math.max(1, ((section.end_s - section.start_s) / durationS) * innerW);
        return (
          <rect
            key={section.id}
            x={x}
            y={padY}
            width={w}
            height={innerH}
            fill={SECTION_FILLS[index % SECTION_FILLS.length]}
            stroke="rgba(139,146,152,0.15)"
            strokeWidth={0.5}
          />
        );
      })}

      {blocks.map((block) => {
        const x = padX + (block.start_s / durationS) * innerW;
        const w = Math.max(2, ((block.end_s - block.start_s) / durationS) * innerW);
        const selected = block.id === activeId;
        return (
          <rect
            key={block.id}
            x={x}
            y={padY}
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

      {downbeats.map((timeS) => {
        const x = padX + (timeS / durationS) * innerW;
        return (
          <line
            key={`downbeat-${timeS}`}
            x1={x}
            x2={x}
            y1={WAVEFORM_HEIGHT - padY - 8}
            y2={WAVEFORM_HEIGHT - padY}
            stroke={DOWNBEAT}
            strokeWidth={2}
          />
        );
      })}

      {markers.map((transient) => {
        const timeS = transient.timestamp_ms / 1000;
        const x = padX + (timeS / durationS) * innerW;
        return (
          <line
            key={`${transient.timestamp_ms}-${transient.type}`}
            x1={x}
            x2={x}
            y1={padY}
            y2={WAVEFORM_HEIGHT - padY}
            stroke={transientColor(transient.type)}
            strokeWidth={transient.type === "drop" ? 2.5 : 1}
            opacity={transient.type === "percussive" ? 0.45 : 0.9}
          />
        );
      })}

      {timeTicks.map((timeS) => {
        const x = padX + (timeS / durationS) * innerW;
        const anchor = timeS <= 0 ? "start" : timeS >= durationS - 0.5 ? "end" : "middle";
        return (
          <g key={`tick-${timeS}`}>
            <line
              x1={x}
              x2={x}
              y1={WAVEFORM_HEIGHT - 4}
              y2={WAVEFORM_HEIGHT + 5}
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

export { blockPixelRange, scopeWidth, WAVEFORM_HEIGHT as SCOPE_HEIGHT };
