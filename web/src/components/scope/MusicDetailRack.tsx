import { memo, useEffect, useId, useMemo, useRef, useState } from "react";
import type { ChromaGram, ScopeLaneSeries } from "../../types";
import { subscribePlayhead, getLastPlayheadS } from "../../utils/playheadBus";
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
  /** Absolute track time where block-local playhead 0 maps; omit to hide transport playhead. */
  playheadAnchorS?: number;
  defaultOpen?: boolean;
}

export function musicDetailLaneCount(
  lanes: ScopeLaneSeries[],
  chroma: ChromaGram | null,
): number {
  const hasChroma = chroma != null && chroma.frames.length > 0;
  return lanes.length + (hasChroma ? 1 : 0);
}

export function musicDetailHasContent(
  lanes: ScopeLaneSeries[],
  chroma: ChromaGram | null,
): boolean {
  return musicDetailLaneCount(lanes, chroma) > 0;
}

interface MusicDetailRackToggleProps {
  open: boolean;
  laneCount: number;
  onToggle: () => void;
  className?: string;
  panelId?: string;
}

export function MusicDetailRackToggle({
  open,
  laneCount,
  onToggle,
  className = "",
  panelId,
}: MusicDetailRackToggleProps) {
  const generatedId = useId();
  const controlsId = panelId ?? generatedId;

  return (
    <button
      type="button"
      className={`flex w-full items-center justify-between rounded border border-monitor-border bg-[#101214] px-3 py-2 text-left transition hover:border-scope-dim ${className}`}
      aria-expanded={open}
      aria-controls={controlsId}
      onClick={onToggle}
    >
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-monitor-muted">
        Music detail
      </span>
      <span className="font-mono text-[10px] text-monitor-muted">
        {open ? "Hide" : "Show"} · {laneCount} lane{laneCount === 1 ? "" : "s"}
      </span>
    </button>
  );
}

interface MusicDetailRackChartProps {
  lanes: ScopeLaneSeries[];
  chroma: ChromaGram | null;
  window: ScopeWindow;
  viewWidth: number;
  playheadAnchorS?: number;
  panelId?: string;
}

function syncPlayheadLine(
  timeS: number,
  line: SVGLineElement | null,
  window: ScopeWindow,
  plotX: number,
  innerW: number,
  playheadAnchorS: number,
): void {
  if (!line) return;
  const duration = window.endS - window.startS;
  const localS = timeS + playheadAnchorS - window.startS;
  if (localS < 0 || localS > duration + 0.001) {
    line.setAttribute("opacity", "0");
    return;
  }
  const x = timeToX(localS, duration, plotX, innerW);
  line.setAttribute("x1", String(x));
  line.setAttribute("x2", String(x));
  line.setAttribute("opacity", "0.95");
}

export const MusicDetailRackChart = memo(function MusicDetailRackChart({
  lanes,
  chroma,
  window,
  viewWidth,
  playheadAnchorS,
  panelId: panelIdProp,
}: MusicDetailRackChartProps) {
  const generatedId = useId();
  const panelId = panelIdProp ?? generatedId;
  const [hoverS, setHoverS] = useState<number | null>(null);
  const playheadLineRef = useRef<SVGLineElement>(null);
  const windowRef = useRef(window);
  windowRef.current = window;
  const playheadAnchorRef = useRef(playheadAnchorS);
  playheadAnchorRef.current = playheadAnchorS;
  const showPlayhead = playheadAnchorS != null;

  const durationS = windowDuration(window);
  const hasChroma = chroma != null && chroma.frames.length > 0;

  const plotX = SCOPE_GUTTER_WIDTH;
  const innerW = viewWidth - plotX - SCOPE_PAD_X;
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

  useEffect(() => {
    if (!showPlayhead) return;
    const onPlayhead = (timeS: number) => {
      syncPlayheadLine(
        timeS,
        playheadLineRef.current,
        windowRef.current,
        plotX,
        innerW,
        playheadAnchorRef.current!,
      );
    };
    const unsubscribe = subscribePlayhead(onPlayhead);
    return unsubscribe;
  }, [innerW, plotX, showPlayhead]);

  useEffect(() => {
    if (!showPlayhead) return;
    syncPlayheadLine(
      getLastPlayheadS(),
      playheadLineRef.current,
      windowRef.current,
      plotX,
      innerW,
      playheadAnchorRef.current!,
    );
  }, [innerW, plotX, showPlayhead]);

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
        hoverS={hoverS}
      />
    );
    cursorY += SCOPE_LANE_HEIGHT;
    return element;
  });

  return (
    <div className="pb-1">
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
        <line
          ref={playheadLineRef}
          x1={plotX}
          x2={plotX}
          y1={0}
          y2={lanesHeight}
          stroke="#E8EAED"
          strokeWidth={1.25}
          opacity={0}
          style={{ pointerEvents: "none" }}
        />
      </svg>
    </div>
  );
});

export const MusicDetailRack = memo(function MusicDetailRack({
  lanes,
  chroma,
  window,
  viewWidth,
  playheadAnchorS,
  defaultOpen = false,
}: MusicDetailRackProps) {
  const panelId = useId();
  const [open, setOpen] = useState(defaultOpen);
  const laneCount = musicDetailLaneCount(lanes, chroma);

  if (!musicDetailHasContent(lanes, chroma)) return null;

  return (
    <div className="space-y-1">
      <MusicDetailRackToggle
        open={open}
        laneCount={laneCount}
        onToggle={() => setOpen((value) => !value)}
        panelId={panelId}
      />

      {open && (
        <MusicDetailRackChart
          lanes={lanes}
          chroma={chroma}
          window={window}
          viewWidth={viewWidth}
          playheadAnchorS={playheadAnchorS}
          panelId={panelId}
        />
      )}
    </div>
  );
});
