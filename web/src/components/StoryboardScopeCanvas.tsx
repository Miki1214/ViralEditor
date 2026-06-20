import { useMemo } from "react";
import type { SpatialFxSettings, StoryboardPayload, WaveformPayload } from "../types";
import { planSpatialFxMarkers } from "../utils/spatialFxMarkers";
import { slotColorForIndex } from "../utils/slotColors";

interface StoryboardScopeCanvasProps {
  waveform: WaveformPayload;
  storyboard: StoryboardPayload;
  selectedSlotId: string | null;
  playheadS?: number;
  spatialFx?: SpatialFxSettings;
  onSelectSlot?: (slotId: string) => void;
}

const TRACE = "#3DDC84";
const ZOOM = "#F4C430";
const ROTATE = "#38BDF8";
const HEIGHT = 72;
const PAD_X = 4;
const PAD_Y = 8;

function blockPoints(
  points: WaveformPayload["points"],
  blockStartS: number,
  blockEndS: number,
): Array<{ t: number; v: number }> {
  return points
    .filter((point) => point.t >= blockStartS - 0.001 && point.t <= blockEndS + 0.001)
    .map((point) => ({ t: point.t - blockStartS, v: point.v }));
}

export function StoryboardScopeCanvas({
  waveform,
  storyboard,
  selectedSlotId,
  playheadS = 0,
  spatialFx,
  onSelectSlot,
}: StoryboardScopeCanvasProps) {
  const blockStartS = storyboard.music_start_s;
  const blockDurationS = storyboard.total_duration_s;
  const fxSettings = spatialFx ?? storyboard.spatial_fx;
  const orderedSlots = useMemo(
    () => [...storyboard.slots].sort((a, b) => a.order - b.order),
    [storyboard.slots],
  );

  const points = useMemo(
    () => blockPoints(waveform.points, blockStartS, storyboard.music_end_s),
    [waveform.points, blockStartS, storyboard.music_end_s],
  );

  const fxMarkers = useMemo(
    () =>
      planSpatialFxMarkers(waveform.transients, {
        musicStartS: storyboard.music_start_s,
        musicEndS: storyboard.music_end_s,
        maxEventsPerSecond: fxSettings.max_events_per_second,
        enabled: fxSettings.enabled,
      }),
    [
      waveform.transients,
      storyboard.music_start_s,
      storyboard.music_end_s,
      fxSettings.enabled,
      fxSettings.max_events_per_second,
    ],
  );

  const viewWidth = 640;
  const innerW = viewWidth - PAD_X * 2;
  const innerH = HEIGHT - PAD_Y * 2;

  const waveformPath = useMemo(() => {
    if (points.length === 0 || blockDurationS <= 0) return "";
    return points
      .map((point, index) => {
        const x = PAD_X + (point.t / blockDurationS) * innerW;
        const y = PAD_Y + innerH - point.v * innerH;
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
    <div className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-monitor-muted">
          Music block
        </p>
        <p className="font-mono text-[10px] text-monitor-muted">
          {blockDurationS.toFixed(1)}s window
        </p>
      </div>
      {fxSettings.enabled && fxMarkers.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 font-mono text-[10px] text-monitor-muted">
          <span className="inline-flex items-center gap-1">
            <span className="inline-block h-2 w-0.5 rounded-full bg-[#F4C430]" aria-hidden />
            Zoom
          </span>
          <span className="inline-flex items-center gap-1">
            <span
              className="inline-block h-1.5 w-1.5 rounded-full bg-[#38BDF8]"
              aria-hidden
            />
            Rotate
          </span>
        </div>
      )}
      <svg
        viewBox={`0 0 ${viewWidth} ${HEIGHT}`}
        width="100%"
        height={HEIGHT}
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
        {orderedSlots.map((slot, index) => {
          const selected = slot.id === selectedSlotId;
          const color = slotColorForIndex(index);
          const x = PAD_X + (slot.out_start_s / blockDurationS) * innerW;
          const w = Math.max(
            2,
            ((slot.out_end_s - slot.out_start_s) / blockDurationS) * innerW,
          );
          return (
            <g key={slot.id}>
              <rect
                x={x}
                y={PAD_Y}
                width={w}
                height={innerH}
                fill={selected ? color.fillActive : color.fill}
                stroke={selected ? color.stroke : color.border}
                strokeWidth={selected ? 2 : 1.25}
                rx={2}
              />
              {selected && (
                <text
                  x={x + w / 2}
                  y={PAD_Y + 10}
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
                  const y = PAD_Y + innerH - point.v * innerH;
                  return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
                })
                .join(" ");
              return (
                <g key={`highlight-${slot.id}`}>
                  <clipPath id={`slot-clip-${slot.id}`}>
                    <rect x={clipStart} y={PAD_Y} width={clipWidth} height={innerH} />
                  </clipPath>
                  <path
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

        {fxMarkers.map((marker, index) => {
          if (blockDurationS <= 0) return null;
          const x = PAD_X + (marker.timeS / blockDurationS) * innerW;
          if (marker.kind === "zoom") {
            return (
              <g key={`fx-zoom-${index}-${marker.timeS}`} style={{ pointerEvents: "none" }}>
                <line
                  x1={x}
                  x2={x}
                  y1={PAD_Y}
                  y2={PAD_Y + innerH * 0.55}
                  stroke={ZOOM}
                  strokeWidth={2}
                  opacity={0.95}
                />
                <polygon
                  points={`${x},${PAD_Y + 2} ${x - 3},${PAD_Y + 8} ${x + 3},${PAD_Y + 8}`}
                  fill={ZOOM}
                  opacity={0.95}
                />
              </g>
            );
          }
          return (
            <g key={`fx-rotate-${index}-${marker.timeS}`} style={{ pointerEvents: "none" }}>
              <line
                x1={x}
                x2={x}
                y1={PAD_Y + innerH * 0.45}
                y2={PAD_Y + innerH}
                stroke={ROTATE}
                strokeWidth={1.5}
                opacity={0.9}
              />
              <circle cx={x} cy={PAD_Y + innerH - 3} r={2.5} fill={ROTATE} opacity={0.95} />
            </g>
          );
        })}

        {waveform.downbeats
          .filter(
            (timeS) =>
              timeS >= blockStartS - 0.001 && timeS <= storyboard.music_end_s + 0.001,
          )
          .map((timeS) => {
            const relative = timeS - blockStartS;
            const x = PAD_X + (relative / blockDurationS) * innerW;
            return (
              <line
                key={`downbeat-${timeS}`}
                x1={x}
                x2={x}
                y1={HEIGHT - PAD_Y - 6}
                y2={HEIGHT - PAD_Y}
                stroke="rgba(139,146,152,0.45)"
                strokeWidth={1.5}
                style={{ pointerEvents: "none" }}
              />
            );
          })}

        {orderedSlots.slice(0, -1).map((slot) => {
          const x = PAD_X + (slot.out_end_s / blockDurationS) * innerW;
          return (
            <line
              key={`boundary-${slot.id}`}
              x1={x}
              x2={x}
              y1={PAD_Y}
              y2={PAD_Y + innerH}
              stroke="rgba(139,146,152,0.35)"
              strokeWidth={1}
              strokeDasharray="3 2"
              style={{ pointerEvents: "none" }}
            />
          );
        })}

        {blockDurationS > 0 && (
          <line
            x1={PAD_X + (playheadS / blockDurationS) * innerW}
            x2={PAD_X + (playheadS / blockDurationS) * innerW}
            y1={PAD_Y}
            y2={PAD_Y + innerH}
            stroke="#E8EAED"
            strokeWidth={1.5}
            style={{ pointerEvents: "none" }}
          />
        )}
      </svg>
    </div>
  );
}
