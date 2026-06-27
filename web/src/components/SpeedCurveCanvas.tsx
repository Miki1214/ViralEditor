import { useEffect, useMemo, useRef, useState } from "react";
import type { MusicSection, SpeedCurvePoint } from "../types";

interface SpeedCurveCanvasProps {
  durationS: number;
  curve: SpeedCurvePoint[];
  sections: MusicSection[];
  downbeats: number[];
  minSpeed: number;
  maxSpeed: number;
  animateKey: string;
}

const TRACE = "#3DDC84";
const SLOW = "rgba(244,196,48,0.18)";
const BASS = "#38BDF8";
const MUTED = "#8B9298";
const DOWNBEAT = "rgba(139,146,152,0.35)";

function speedToY(
  speed: number,
  minSpeed: number,
  maxSpeed: number,
  innerH: number,
  padY: number,
): number {
  const lo = Math.log(Math.max(minSpeed, 0.5));
  const hi = Math.log(Math.max(maxSpeed, minSpeed + 0.1));
  const value = Math.log(Math.max(speed, 0.5));
  const norm = hi > lo ? (value - lo) / (hi - lo) : 0.5;
  return padY + innerH - norm * innerH;
}

export function SpeedCurveCanvas({
  durationS,
  curve,
  sections,
  downbeats,
  minSpeed,
  maxSpeed,
  animateKey,
}: SpeedCurveCanvasProps) {
  const width = 960;
  const height = 72;
  const padX = 4;
  const padY = 8;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;
  const pathRef = useRef<SVGPathElement | null>(null);
  const [drawn, setDrawn] = useState(false);

  const path = useMemo(() => {
    if (curve.length === 0 || durationS <= 0) return "";
    return curve
      .map((point, index) => {
        const x = padX + (point.t / durationS) * innerW;
        const y = speedToY(point.speed, minSpeed, maxSpeed, innerH, padY);
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
  }, [curve, durationS, innerW, innerH, minSpeed, maxSpeed]);

  useEffect(() => {
    setDrawn(false);
    const node = pathRef.current;
    if (!node || !path) {
      setDrawn(true);
      return;
    }
    const length = node.getTotalLength();
    node.style.strokeDasharray = `${length}`;
    node.style.strokeDashoffset = `${length}`;
    const frame = requestAnimationFrame(() => {
      node.style.transition = "stroke-dashoffset 600ms ease-out";
      node.style.strokeDashoffset = "0";
      setDrawn(true);
    });
    return () => cancelAnimationFrame(frame);
  }, [path, animateKey]);

  const slowBands = useMemo(() => {
    if (curve.length === 0) return [];
    const bands: { x: number; w: number }[] = [];
    for (const point of curve) {
      if (!point.is_slow_zone) continue;
      const x = padX + (point.t / durationS) * innerW;
      bands.push({ x: x - 2, w: 4 });
    }
    return bands;
  }, [curve, durationS, innerW]);

  return (
    <svg
      id="speed-curve-svg"
      viewBox={`0 0 ${width} ${height}`}
      className="h-[72px] w-full min-w-[320px] overflow-visible rounded border border-monitor-border bg-[#141618]"
      role="img"
      aria-label="Speed velocity lane"
    >
      {sections.map((section, index) => {
        const x = padX + (section.start_s / durationS) * innerW;
        const w = Math.max(1, ((section.end_s - section.start_s) / durationS) * innerW);
        return (
          <rect
            id={`speed-curve-section-${section.id}`}
            key={section.id}
            x={x}
            y={padY}
            width={w}
            height={innerH}
            fill={`rgba(139,146,152,${0.04 + (index % 3) * 0.02})`}
          />
        );
      })}

      {slowBands.map((band, index) => (
        <rect
          id={`speed-curve-slow-${index}`}
          key={`slow-${index}`}
          x={band.x}
          y={padY}
          width={band.w}
          height={innerH}
          fill={SLOW}
        />
      ))}

      {downbeats.map((time) => {
        const x = padX + (time / durationS) * innerW;
        return (
          <line
            id={`speed-curve-db-${time}`}
            key={`db-${time}`}
            x1={x}
            x2={x}
            y1={padY}
            y2={padY + innerH}
            stroke={DOWNBEAT}
            strokeWidth={1}
          />
        );
      })}

      {curve
        .filter((point) => point.is_bass_accent)
        .map((point) => {
          const x = padX + (point.t / durationS) * innerW;
          const y = speedToY(point.speed, minSpeed, maxSpeed, innerH, padY);
          return (
            <circle id={`speed-curve-bass-${point.t}`} key={`bass-${point.t}`} cx={x} cy={y} r={2.5} fill={BASS} opacity={0.9} />
          );
        })}

      {path && (
        <path
          id="speed-curve-path"
          ref={pathRef}
          d={path}
          fill="none"
          stroke={TRACE}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{
            filter: "drop-shadow(0 0 4px rgba(61,220,132,0.55))",
            opacity: drawn ? 1 : 0.85,
          }}
        />
      )}

      <text id="speed-curve-max-label" x={width - padX - 2} y={padY + 10} textAnchor="end" fill={MUTED} fontSize={9} fontFamily="JetBrains Mono">
        {maxSpeed.toFixed(1)}x
      </text>
      <text id="speed-curve-min-label" x={width - padX - 2} y={padY + innerH - 2} textAnchor="end" fill={MUTED} fontSize={9} fontFamily="JetBrains Mono">
        {minSpeed.toFixed(1)}x
      </text>
    </svg>
  );
}
