import { useId, useMemo, useState } from "react";
import type { ChromaGram, ScopeLaneSeries } from "../../types";
import { ChromaHeatmap } from "./ChromaHeatmap";
import { ScopeLane } from "./ScopeLane";
import {
  buildTimeTicks,
  formatScopeTime,
  LABEL_COLOR,
  RULER_BG,
  SCOPE_CHROMA_HEIGHT,
  SCOPE_GUTTER_WIDTH,
  SCOPE_LANE_HEIGHT,
  SCOPE_PAD_X,
  SCOPE_RULER_HEIGHT,
  TICK_COLOR,
} from "./scopeTheme";
import {
  cropChromaToWindow,
  cropPointsToWindow,
  timeToX,
  windowDuration,
  xToTime,
  type ScopeWindow,
} from "./scopeWindow";

interface MusicDetailRackProps {
  lanes: ScopeLaneSeries[];
  chroma: ChromaGram | null;
  window: ScopeWindow;
  viewWidth: number;
  playheadS?: number | null;
  playheadLocalS?: number | null;
  defaultOpen?: boolean;
}

export function MusicDetailRack({
  lanes,
  chroma,
  window,
  viewWidth,
  playheadS = null,
  playheadLocalS = null,
  defaultOpen = false,
}: MusicDetailRackProps) {
  const panelId = useId();
  const [open, setOpen] = useState(defaultOpen);
  const [hoverS, setHoverS] = useState<number | null>(null);

  const durationS = windowDuration(window);
  const hasChroma = chroma != null && chroma.frames.length > 0;
  const hasContent = lanes.length > 0 || hasChroma;
  if (!hasContent) return null;

  const plotX = SCOPE_GUTTER_WIDTH;
  const innerW = viewWidth - plotX - SCOPE_PAD_X;
  const laneCount = lanes.length + (hasChroma ? 1 : 0);
  const lanesHeight = lanes.length * SCOPE_LANE_HEIGHT + (hasChroma ? SCOPE_CHROMA_HEIGHT : 0);
  const totalHeight = lanesHeight + SCOPE_RULER_HEIGHT;

  const croppedLanes = useMemo(
    () =>
      lanes.map((lane) => ({
        ...lane,
        points: cropPointsToWindow(lane.points, window),
      })),
    [lanes, window],
  );

  const croppedChroma = useMemo(
    () => (chroma ? cropChromaToWindow(chroma, window) : null),
    [chroma, window],
  );

  const timeTicks = useMemo(
    () => buildTimeTicks(durationS, innerW),
    [durationS, innerW],
  );

  const localPlayhead =
    playheadLocalS != null
      ? playheadLocalS
      : playheadS != null && playheadS >= window.startS && playheadS <= window.endS
        ? playheadS - window.startS
        : null;

  const handlePointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const scale = viewWidth / rect.width;
    const svgX = (event.clientX - rect.left) * scale;
    setHoverS(xToTime(svgX, durationS, plotX, innerW));
  };

  let cursorY = 0;
  const laneElements = croppedLanes.map((lane) => {
    const element = (
      <ScopeLane
        key={lane.id}
        laneId={lane.id}
        label={lane.label}
        points={lane.points}
        window={{ startS: 0, endS: durationS }}
        viewWidth={viewWidth}
        height={SCOPE_LANE_HEIGHT}
        y={cursorY}
        playheadS={localPlayhead}
        hoverS={hoverS}
      />
    );
    cursorY += SCOPE_LANE_HEIGHT;
    return element;
  });

  return (
    <div className="space-y-1">
      <button
        type="button"
        className="flex w-full items-center justify-between rounded border border-monitor-border bg-[#101214] px-3 py-2 text-left transition hover:border-scope-dim"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((value) => !value)}
      >
        <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-monitor-muted">
          Music detail
        </span>
        <span className="font-mono text-[10px] text-monitor-muted">
          {open ? "Hide" : "Show"} · {laneCount} lane{laneCount === 1 ? "" : "s"}
        </span>
      </button>

      {open && (
        <div className="overflow-x-auto pb-1">
          <svg
            id={panelId}
            viewBox={`0 0 ${viewWidth} ${totalHeight}`}
            width={viewWidth}
            height={totalHeight}
            className="block max-w-none rounded border border-monitor-border bg-[#141618]"
            role="img"
            aria-label="Music detail analyzer rack"
            onPointerMove={handlePointerMove}
            onPointerLeave={() => setHoverS(null)}
          >
            {laneElements}
            {hasChroma && croppedChroma && (
              <ChromaHeatmap
                chroma={croppedChroma}
                window={{ startS: 0, endS: durationS }}
                viewWidth={viewWidth}
                y={cursorY}
                playheadS={localPlayhead}
                hoverS={hoverS}
              />
            )}
            <rect
              x={0}
              y={lanesHeight}
              width={viewWidth}
              height={SCOPE_RULER_HEIGHT}
              fill={RULER_BG}
            />
            <line
              x1={plotX}
              x2={viewWidth - SCOPE_PAD_X}
              y1={lanesHeight}
              y2={lanesHeight}
              stroke={TICK_COLOR}
              strokeWidth={1}
            />
            {timeTicks.map((timeS) => {
              const x = timeToX(timeS, durationS, plotX, innerW);
              const anchor =
                timeS <= 0 ? "start" : timeS >= durationS - 0.5 ? "end" : "middle";
              return (
                <g key={`detail-tick-${timeS}`}>
                  <line
                    x1={x}
                    x2={x}
                    y1={lanesHeight - 3}
                    y2={lanesHeight + 4}
                    stroke={TICK_COLOR}
                    strokeWidth={1}
                  />
                  <text
                    x={x}
                    y={totalHeight - 5}
                    fill={LABEL_COLOR}
                    fontSize={9}
                    fontFamily="JetBrains Mono, ui-monospace, monospace"
                    textAnchor={anchor}
                  >
                    {formatScopeTime(timeS)}
                  </text>
                </g>
              );
            })}
            {hoverS != null && (
              <line
                x1={timeToX(hoverS, durationS, plotX, innerW)}
                x2={timeToX(hoverS, durationS, plotX, innerW)}
                y1={0}
                y2={lanesHeight}
                stroke="#E8EAED"
                strokeWidth={1}
                opacity={0.35}
              />
            )}
            {localPlayhead != null && (
              <line
                x1={timeToX(localPlayhead, durationS, plotX, innerW)}
                x2={timeToX(localPlayhead, durationS, plotX, innerW)}
                y1={0}
                y2={lanesHeight}
                stroke="#E8EAED"
                strokeWidth={1.25}
                opacity={0.95}
              />
            )}
          </svg>
        </div>
      )}
    </div>
  );
}
