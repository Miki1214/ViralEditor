import { useMemo } from "react";
import type { MusicBlock, Transient, WaveformPoint } from "../types";

interface ScopeCanvasProps {
  durationS: number;
  points: WaveformPoint[];
  transients: Transient[];
  blocks: MusicBlock[];
  selectedBlockId: string | null;
  playingBlockId: string | null;
}

const TRACE = "#3DDC84";
const DROP = "#F4C430";
const BASS = "#38BDF8";
const MUTED = "#8B9298";

function transientColor(type: Transient["type"]): string {
  if (type === "drop") return DROP;
  if (type === "bass") return BASS;
  return MUTED;
}

export function ScopeCanvas({
  durationS,
  points,
  transients,
  blocks,
  selectedBlockId,
  playingBlockId,
}: ScopeCanvasProps) {
  const width = 960;
  const height = 72;
  const padX = 4;
  const padY = 8;

  const path = useMemo(() => {
    if (points.length === 0 || durationS <= 0) return "";
    const innerW = width - padX * 2;
    const innerH = height - padY * 2;
    return points
      .map((point, index) => {
        const x = padX + (point.t / durationS) * innerW;
        const y = padY + innerH - point.v * innerH;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
  }, [points, durationS]);

  const activeId = playingBlockId ?? selectedBlockId;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-[72px] w-full min-w-[320px] overflow-visible rounded border border-monitor-border bg-[#141618]"
      role="img"
      aria-label="Audio scope waveform"
    >
      {blocks.map((block) => {
        const innerW = width - padX * 2;
        const x = padX + (block.start_s / durationS) * innerW;
        const w = Math.max(2, ((block.end_s - block.start_s) / durationS) * innerW);
        const selected = block.id === activeId;
        return (
          <rect
            key={block.id}
            x={x}
            y={padY}
            width={w}
            height={height - padY * 2}
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
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      )}

      {transients.map((transient) => {
        const timeS = transient.timestamp_ms / 1000;
        const x = padX + (timeS / durationS) * (width - padX * 2);
        return (
          <line
            key={`${transient.timestamp_ms}-${transient.type}`}
            x1={x}
            x2={x}
            y1={padY}
            y2={height - padY}
            stroke={transientColor(transient.type)}
            strokeWidth={transient.type === "drop" ? 2 : 1}
            opacity={transient.type === "percussive" ? 0.45 : 0.9}
          />
        );
      })}
    </svg>
  );
}
