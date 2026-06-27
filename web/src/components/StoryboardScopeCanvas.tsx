import { memo, useEffect, useMemo, useRef } from "react";
import type { SpatialFxSettings, StoryboardPayload, WaveformPayload } from "../types";
import { subscribePlayhead } from "../utils/playheadBus";
import { planSpatialFxMarkers, assignedSlotBoundaryTimesAbs, blockWindowEndS } from "../utils/spatialFxMarkers";
import { slotColorForIndex } from "../utils/slotColors";
import { ScopeMarkerStrip } from "./scope/ScopeMarkerStrip";
import { SectionRibbon } from "./scope/SectionRibbon";
import { layoutSectionSwimlanes } from "./scope/sectionSwimlanes";
import {
  buildTimeTicks,
  formatScopeTime,
  LABEL_COLOR,
  RULER_BG,
  SCOPE_MARKER_STRIP_HEIGHT,
  SCOPE_PAD_X,
  SCOPE_RULER_HEIGHT,
  TICK_COLOR,
  TRACE,
} from "./scope/scopeTheme";
import { cropTimesToWindow, timeToX, type ScopeWindow } from "./scope/scopeWindow";

interface StoryboardScopeCanvasProps {
  waveform: WaveformPayload;
  storyboard: StoryboardPayload;
  selectedSlotId: string | null;
  spatialFx?: SpatialFxSettings;
  onSelectSlot?: (slotId: string) => void;
}

const WAVEFORM_HEIGHT = 72;
const PAD_X = SCOPE_PAD_X;
const PAD_Y = 8;
const VIEW_WIDTH = 640;

function blockPoints(
  points: WaveformPayload["points"],
  blockStartS: number,
  blockEndS: number,
): Array<{ t: number; v: number }> {
  return points
    .filter((point) => point.t >= blockStartS - 0.001 && point.t <= blockEndS + 0.001)
    .map((point) => ({ t: point.t - blockStartS, v: point.v }));
}

export const StoryboardScopeCanvas = memo(function StoryboardScopeCanvas({
  waveform,
  storyboard,
  selectedSlotId,
  spatialFx,
  onSelectSlot,
}: StoryboardScopeCanvasProps) {
  const blockStartS = storyboard.music_start_s;
  const blockEndS = storyboard.music_end_s;
  const blockDurationS = storyboard.total_duration_s;
  const scopeWindow: ScopeWindow = { startS: blockStartS, endS: blockEndS };
  const fxSettings = spatialFx ?? storyboard.spatial_fx;
  const orderedSlots = useMemo(
    () => [...storyboard.slots].sort((a, b) => a.order - b.order),
    [storyboard.slots],
  );

  const points = useMemo(
    () => blockPoints(waveform.points, blockStartS, blockEndS),
    [waveform.points, blockStartS, blockEndS],
  );

  const localDownbeats = useMemo(
    () => cropTimesToWindow(waveform.downbeats, scopeWindow),
    [waveform.downbeats, scopeWindow],
  );

  const slotBoundaryTimesAbs = useMemo(
    () =>
      assignedSlotBoundaryTimesAbs(
        orderedSlots,
        blockStartS,
        blockWindowEndS(blockStartS, blockEndS, blockDurationS),
      ),
    [orderedSlots, blockStartS, blockEndS, blockDurationS],
  );

  const fxMarkers = useMemo(
    () =>
      planSpatialFxMarkers(waveform.transients, {
        musicStartS: storyboard.music_start_s,
        musicEndS: storyboard.music_end_s,
        totalDurationS: blockDurationS,
        maxEventsPerSecond: fxSettings.max_events_per_second,
        enabled: fxSettings.enabled,
        lanes: waveform.lanes,
        downbeats: waveform.downbeats,
        beats: waveform.beats,
        slotBoundaryTimesAbs,
        pan: {
          translateEnabled: fxSettings.translate_enabled ?? true,
          panBeatMode: fxSettings.pan_beat_mode ?? "auto",
          panEnergyThreshold: fxSettings.pan_energy_threshold ?? 0.45,
          panEnergyFloor: fxSettings.pan_energy_floor ?? 0.2,
          panHookEnabled: fxSettings.pan_hook_enabled ?? true,
          panHookByS: fxSettings.pan_hook_by_s ?? 1.0,
        },
      }),
    [
      waveform.transients,
      waveform.lanes,
      waveform.downbeats,
      waveform.beats,
      storyboard.music_start_s,
      storyboard.music_end_s,
      slotBoundaryTimesAbs,
      fxSettings.enabled,
      fxSettings.max_events_per_second,
      fxSettings.translate_enabled,
      fxSettings.pan_beat_mode,
      fxSettings.pan_energy_threshold,
      fxSettings.pan_hook_enabled,
      fxSettings.pan_hook_by_s,
    ],
  );

  const viewWidth = VIEW_WIDTH;
  const sectionLayout = useMemo(
    () => layoutSectionSwimlanes(waveform.sections, scopeWindow, viewWidth),
    [waveform.sections, scopeWindow, viewWidth],
  );
  const waveformTop = sectionLayout.height;
  const rulerTop = waveformTop + WAVEFORM_HEIGHT;
  const markerStripTop = rulerTop + SCOPE_RULER_HEIGHT;
  const totalHeight =
    sectionLayout.height + WAVEFORM_HEIGHT + SCOPE_RULER_HEIGHT + SCOPE_MARKER_STRIP_HEIGHT;
  const innerW = viewWidth - PAD_X * 2;
  const innerH = WAVEFORM_HEIGHT - PAD_Y * 2;
  const playheadLineRef = useRef<SVGLineElement>(null);
  const blockDurationRef = useRef(blockDurationS);
  blockDurationRef.current = blockDurationS;

  useEffect(() => {
    return subscribePlayhead((timeS) => {
      const duration = blockDurationRef.current;
      const line = playheadLineRef.current;
      if (!line || duration <= 0) return;
      const x = PAD_X + (timeS / duration) * innerW;
      line.setAttribute("x1", String(x));
      line.setAttribute("x2", String(x));
    });
  }, [innerW]);

  const timeTicks = useMemo(
    () => buildTimeTicks(blockDurationS, innerW),
    [blockDurationS, innerW],
  );

  const waveformPath = useMemo(() => {
    if (points.length === 0 || blockDurationS <= 0) return "";
    return points
      .map((point, index) => {
        const x = PAD_X + (point.t / blockDurationS) * innerW;
        const y = waveformTop + PAD_Y + innerH - point.v * innerH;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
  }, [points, blockDurationS, innerW, innerH]);

  const slotAtX = (clientX: number, rect: DOMRect): string | null => {
    if (blockDurationS <= 0) return null;
    const ratio = Math.max(0, Math.min(1, (clientX - rect.left - PAD_X) / innerW));
    const timeS = ratio * blockDurationS;
    const hit = orderedSlots.find(
      (slot) => timeS >= slot.out_start_s - 0.001 && timeS < slot.out_end_s - 0.001,
    );
    return hit?.id ?? null;
  };

  return (
    <div id="storyboard-scope-container" className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <p id="storyboard-scope-label" className="font-mono text-[10px] uppercase tracking-[0.16em] text-monitor-muted">
          Music block
        </p>
        <p id="storyboard-scope-window-size" className="font-mono text-[10px] text-monitor-muted">
          {blockDurationS.toFixed(1)}s window
        </p>
      </div>
      {fxSettings.enabled && fxMarkers.length > 0 && (
        <div id="storyboard-scope-fx-legend" className="flex flex-wrap items-center gap-3 font-mono text-[10px] text-monitor-muted">
          <span id="storyboard-scope-fx-zoom" className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-0.5 rounded-full bg-[#F4C430]" aria-hidden />
            Zoom
          </span>
          <span id="storyboard-scope-fx-rotate" className="inline-flex items-center gap-1">
            <span
              className="inline-block h-1.5 w-1.5 rounded-full bg-[#38BDF8]"
              aria-hidden
            />
            Rotate
          </span>
          <span id="storyboard-scope-fx-pan" className="inline-flex items-center gap-1">
            <span
              className="inline-block h-1.5 w-1.5 rounded-full bg-[#A78BFA]"
              aria-hidden
            />
            Pan
          </span>
        </div>
      )}
      <svg
        id="storyboard-scope-svg"
        viewBox={`0 0 ${viewWidth} ${totalHeight}`}
        width="100%"
        height={totalHeight}
        className="block rounded border border-monitor-border bg-[#141618] cursor-pointer"
        role="img"
        aria-label="Storyboard music block waveform"
        onClick={(event) => {
          if (!onSelectSlot) return;
          const rect = event.currentTarget.getBoundingClientRect();
          const slotId = slotAtX(event.clientX, rect);
          if (slotId) onSelectSlot(slotId);
        }}
      >
        <SectionRibbon
          sections={waveform.sections}
          window={scopeWindow}
          viewWidth={viewWidth}
          y={0}
          layout={sectionLayout}
        />
        <rect
          id="storyboard-scope-ruler-bg"
          x={0}
          y={rulerTop}
          width={viewWidth}
          height={SCOPE_RULER_HEIGHT}
          fill={RULER_BG}
        />
        <line
          id="storyboard-scope-ruler-line"
          x1={PAD_X}
          x2={viewWidth - PAD_X}
          y1={rulerTop}
          y2={rulerTop}
          stroke={TICK_COLOR}
          strokeWidth={1}
        />
        {orderedSlots.map((slot, index) => {
          const selected = slot.id === selectedSlotId;
          const color = slotColorForIndex(index);
          const x = PAD_X + (slot.out_start_s / blockDurationS) * innerW;
          const w = Math.max(
            2,
            ((slot.out_end_s - slot.out_start_s) / blockDurationS) * innerW,
          );
          return (
            <g id={`storyboard-scope-slot-${slot.id}`} key={slot.id}>
              <rect
                id={`storyboard-scope-slot-rect-${slot.id}`}
                x={x}
                y={waveformTop + PAD_Y}
                width={w}
                height={innerH}
                fill={selected ? color.fillActive : color.fill}
                stroke={selected ? color.stroke : color.border}
                strokeWidth={selected ? 2 : 1.25}
                rx={2}
              />
              {selected && (
                <text
                  id={`storyboard-scope-slot-text-${slot.id}`}
                  x={x + w / 2}
                  y={waveformTop + PAD_Y + 10}
                  textAnchor="middle"
                  fill={color.stroke}
                  fontSize={8}
                  fontFamily="JetBrains Mono, ui-monospace, monospace"
                  style={{ pointerEvents: "none" }}
                >
                  {slot.label.toUpperCase()}
                </text>
              )}
            </g>
          );
        })}

        {waveformPath && (
          <path
            id="storyboard-scope-waveform"
            d={waveformPath}
            fill="none"
            stroke={TRACE}
            strokeWidth={1.5}
            strokeLinejoin="round"
            strokeLinecap="round"
            style={{ pointerEvents: "none" }}
          />
        )}

        {selectedSlotId &&
          orderedSlots
            .map((slot, index) => ({ slot, index }))
            .filter(({ slot }) => slot.id === selectedSlotId)
            .map(({ slot, index }) => {
              const color = slotColorForIndex(index);
              const clipStart = PAD_X + (slot.out_start_s / blockDurationS) * innerW;
              const clipWidth = Math.max(
                2,
                ((slot.out_end_s - slot.out_start_s) / blockDurationS) * innerW,
              );
              const clipPoints = points.filter(
                (point) =>
                  point.t >= slot.out_start_s - 0.001 && point.t <= slot.out_end_s + 0.001,
              );
              if (clipPoints.length === 0) return null;
              const highlightPath = clipPoints
                .map((point, index) => {
                  const x = PAD_X + (point.t / blockDurationS) * innerW;
                  const y = waveformTop + PAD_Y + innerH - point.v * innerH;
                  return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
                })
                .join(" ");
              return (
                <g id={`storyboard-scope-highlight-${slot.id}`} key={`highlight-${slot.id}`}>
                  <clipPath id={`storyboard-scope-clip-${slot.id}`}>
                    <rect x={clipStart} y={waveformTop + PAD_Y} width={clipWidth} height={innerH} />
                  </clipPath>
                  <path
                    id={`storyboard-scope-highlight-path-${slot.id}`}
                    d={highlightPath}
                    fill="none"
                    stroke={color.stroke}
                    strokeWidth={2.25}
                    strokeLinejoin="round"
                    strokeLinecap="round"
                    clipPath={`url(#slot-clip-${slot.id})`}
                    style={{ pointerEvents: "none" }}
                  />
                </g>
              );
            })}

        <ScopeMarkerStrip
          window={{ startS: 0, endS: blockDurationS }}
          viewWidth={viewWidth}
          y={markerStripTop}
          height={SCOPE_MARKER_STRIP_HEIGHT}
          downbeats={localDownbeats}
          accents={[]}
          fxMarkers={fxSettings.enabled ? fxMarkers : []}
        />

        {orderedSlots.slice(0, -1).map((slot) => {
          const x = PAD_X + (slot.out_end_s / blockDurationS) * innerW;
          return (
            <line
              id={`storyboard-scope-boundary-${slot.id}`}
              key={`boundary-${slot.id}`}
              x1={x}
              x2={x}
              y1={waveformTop + PAD_Y}
              y2={waveformTop + PAD_Y + innerH}
              stroke="rgba(139,146,152,0.35)"
              strokeWidth={1}
              strokeDasharray="3 2"
              style={{ pointerEvents: "none" }}
            />
          );
        })}

        {blockDurationS > 0 && (
          <line
            id="storyboard-scope-playhead"
            ref={playheadLineRef}
            x1={PAD_X}
            x2={PAD_X}
            y1={waveformTop + PAD_Y}
            y2={waveformTop + PAD_Y + innerH}
            stroke="#E8EAED"
            strokeWidth={1.5}
            style={{ pointerEvents: "none" }}
          />
        )}

        {timeTicks.map((timeS) => {
          const x = timeToX(timeS, blockDurationS, PAD_X, innerW);
          const anchor = timeS <= 0 ? "start" : timeS >= blockDurationS - 0.5 ? "end" : "middle";
          return (
            <g id={`storyboard-scope-tick-${timeS}`} key={`tick-${timeS}`} style={{ pointerEvents: "none" }}>
              <line
                id={`storyboard-scope-tick-mark-${timeS}`}
                x1={x}
                x2={x}
                y1={rulerTop + 2}
                y2={rulerTop + 8}
                stroke={TICK_COLOR}
                strokeWidth={1}
              />
              <text
                id={`storyboard-scope-tick-label-${timeS}`}
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
      </svg>
    </div>
  );
});
