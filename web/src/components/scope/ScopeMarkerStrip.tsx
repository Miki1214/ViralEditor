import { useMemo } from "react";
import type { Transient } from "../../types";
import { BASS, DOWNBEAT, DROP, MARKER_STRIP_BG, TICK_COLOR } from "./scopeTheme";
import { decimateTimesBySpacing, timeToX, type ScopeWindow } from "./scopeWindow";

interface ScopeMarkerStripProps {
  window: ScopeWindow;
  viewWidth: number;
  y: number;
  height: number;
  downbeats: number[];
  accents: Transient[];
}

const MIN_DOWNBEAT_SPACING_PX = 14;
const MIN_ACCENT_SPACING_PX = 8;
const MIN_BAR_LABEL_SPACING_PX = 40;

export function ScopeMarkerStrip({
  window,
  viewWidth,
  y,
  height,
  downbeats,
  accents,
}: ScopeMarkerStripProps) {
  const durationS = window.endS - window.startS;
  const padX = 4;
  const innerW = viewWidth - padX * 2;
  const baselineY = y + height - 3;
  const dropHeight = height - 6;
  const bassHeight = Math.round(height * 0.62);
  const downbeatHeight = Math.round(height * 0.5);

  const visibleDownbeats = useMemo(
    () => decimateTimesBySpacing(downbeats, durationS, padX, innerW, MIN_DOWNBEAT_SPACING_PX),
    [downbeats, durationS, innerW, padX],
  );

  const visibleAccents = useMemo(() => {
    if (accents.length === 0 || durationS <= 0) {
      return [];
    }
    const sorted = [...accents].sort(
      (left, right) => left.timestamp_ms - right.timestamp_ms,
    );
    const visible: Transient[] = [];
    let lastX = -Infinity;
    for (const transient of sorted) {
      const timeS = transient.timestamp_ms / 1000;
      const x = timeToX(timeS, durationS, padX, innerW);
      if (x - lastX >= MIN_ACCENT_SPACING_PX) {
        visible.push(transient);
        lastX = x;
      }
    }
    return visible;
  }, [accents, durationS, innerW, padX]);

  const showBarLabels = useMemo(() => {
    if (visibleDownbeats.length < 2) {
      return false;
    }
    const first = timeToX(visibleDownbeats[0] ?? 0, durationS, padX, innerW);
    const second = timeToX(visibleDownbeats[1] ?? 0, durationS, padX, innerW);
    return second - first >= MIN_BAR_LABEL_SPACING_PX;
  }, [visibleDownbeats, durationS, innerW, padX]);

  if (durationS <= 0) {
    return null;
  }

  return (
    <g aria-label="Scope markers">
      <rect x={0} y={y} width={viewWidth} height={height} fill={MARKER_STRIP_BG} />
      <line
        x1={padX}
        x2={viewWidth - padX}
        y1={y}
        y2={y}
        stroke={TICK_COLOR}
        strokeWidth={1}
      />

      {visibleDownbeats.map((timeS) => {
        const barIndex =
          downbeats.findIndex((downbeat) => Math.abs(downbeat - timeS) < 0.001) + 1;
        const x = timeToX(timeS, durationS, padX, innerW);
        return (
          <g key={`downbeat-${timeS}`}>
            <line
              x1={x}
              x2={x}
              y1={baselineY - downbeatHeight}
              y2={baselineY}
              stroke={DOWNBEAT}
              strokeWidth={1.25}
            />
            {showBarLabels && barIndex > 0 && (
              <text
                x={x + 2}
                y={y + 10}
                fill={TICK_COLOR}
                fontSize={8}
                fontFamily="JetBrains Mono, ui-monospace, monospace"
              >
                {barIndex}
              </text>
            )}
          </g>
        );
      })}

      {visibleAccents.map((transient) => {
        const timeS = transient.timestamp_ms / 1000;
        const x = timeToX(timeS, durationS, padX, innerW);
        const isDrop = transient.type === "drop";
        const tickHeight = isDrop ? dropHeight : bassHeight;
        return (
          <line
            key={`${transient.type}-${transient.timestamp_ms}`}
            x1={x}
            x2={x}
            y1={baselineY - tickHeight}
            y2={baselineY}
            stroke={isDrop ? DROP : BASS}
            strokeWidth={isDrop ? 2.5 : 1.75}
            strokeLinecap="round"
          />
        );
      })}
    </g>
  );
}
