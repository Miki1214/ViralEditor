import { DOWNBEAT, TICK_COLOR } from "./scopeTheme";
import { timeToX, type ScopeWindow } from "./scopeWindow";

interface ScopeBeatGridProps {
  beats: number[];
  downbeats: number[];
  window: ScopeWindow;
  viewWidth: number;
  topY: number;
  bottomY: number;
  showBarNumbers?: boolean;
}

export function ScopeBeatGrid({
  beats,
  downbeats,
  window,
  viewWidth,
  topY,
  bottomY,
  showBarNumbers = true,
}: ScopeBeatGridProps) {
  const durationS = window.endS - window.startS;
  const innerW = viewWidth - 8;
  const padX = 4;
  if (durationS <= 0) return null;

  const downbeatSet = new Set(downbeats.map((value) => value.toFixed(3)));

  return (
    <g aria-hidden style={{ pointerEvents: "none" }}>
      {beats.map((timeS) => {
        const key = timeS.toFixed(3);
        if (downbeatSet.has(key)) return null;
        const x = timeToX(timeS, durationS, padX, innerW);
        return (
          <line
            key={`beat-${key}`}
            x1={x}
            x2={x}
            y1={bottomY - 4}
            y2={bottomY}
            stroke={TICK_COLOR}
            strokeWidth={0.75}
            opacity={0.55}
          />
        );
      })}
      {downbeats.map((timeS, index) => {
        const x = timeToX(timeS, durationS, padX, innerW);
        return (
          <g key={`downbeat-${timeS}`}>
            <line
              x1={x}
              x2={x}
              y1={topY}
              y2={bottomY}
              stroke={DOWNBEAT}
              strokeWidth={1.25}
            />
            {showBarNumbers && (
              <text
                x={x + 2}
                y={topY + 9}
                fill={TICK_COLOR}
                fontSize={8}
                fontFamily="JetBrains Mono, ui-monospace, monospace"
              >
                {index + 1}
              </text>
            )}
          </g>
        );
      })}
    </g>
  );
}
