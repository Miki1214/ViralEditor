import { useEffect, useMemo, useState } from "react";
import { fetchStoryboardSegments } from "../api/client";
import type { StoryboardPayload, StoryboardSegmentsDebugPayload } from "../types";

interface StoryboardSegmentsPanelProps {
  jobId: string;
  storyboard: StoryboardPayload;
  selectedSlotId: string | null;
  /** Local crop slider values — refetch after commit. */
  pendingCropKey?: string;
}

export function StoryboardSegmentsPanel({
  jobId,
  storyboard,
  selectedSlotId,
  pendingCropKey = "",
}: StoryboardSegmentsPanelProps) {
  const [expanded, setExpanded] = useState(true);
  const [payload, setPayload] = useState<StoryboardSegmentsDebugPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const hasAssignedClips = storyboard.slots.some((slot) => slot.assigned_clip_id);

  const storyboardKey = useMemo(
    () =>
      storyboard.slots
        .map(
          (slot) =>
            `${slot.id}:${slot.crop_start_s ?? ""}:${slot.crop_end_s ?? ""}:${slot.target_duration_s}`,
        )
        .join("|"),
    [storyboard.slots],
  );

  useEffect(() => {
    if (!hasAssignedClips) {
      setPayload(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchStoryboardSegments(jobId)
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        setError(err instanceof Error ? err.message : String(err));
        setPayload(null);
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [jobId, storyboardKey, pendingCropKey, hasAssignedClips]);

  if (!hasAssignedClips) {
    return null;
  }

  const segmentCount = payload?.slots.length ?? 0;

  return (
    <div id="segments-panel" className="space-y-2 border-t border-monitor-border/60 pt-3">
      <button
        id="segments-panel-toggle-btn"
        type="button"
        className="flex w-full items-center justify-between gap-2 text-left"
        onClick={() => setExpanded((value) => !value)}
        aria-expanded={expanded}
      >
        <span id="segments-panel-title" className="font-mono text-[10px] uppercase tracking-[0.14em] text-monitor-muted">
          Composite segments
          {segmentCount > 0 ? ` · ${segmentCount}` : ""}
        </span>
        <span id="segments-panel-expand-label" className="font-mono text-[10px] text-scope-dim">{expanded ? "Hide" : "Show"}</span>
      </button>

      {expanded && (
        <>
          {loading && (
            <p id="segments-panel-loading" className="font-mono text-[10px] text-monitor-muted">Loading segments…</p>
          )}
          {error && <p id="segments-panel-error" className="font-mono text-[10px] text-red-400">{error}</p>}
          {payload && payload.slots.length > 0 && (
            <div id="segments-panel-table" className="overflow-x-auto rounded border border-monitor-border/50 bg-monitor-bg/30">
              <table className="w-full font-mono text-[10px]">
                <thead id="segments-panel-thead">
                  <tr className="border-b border-monitor-border/40 text-left text-monitor-muted">
                    <th id="segments-panel-th-role" className="px-2 py-1.5 font-normal">Role</th>
                    <th id="segments-panel-th-src" className="px-2 py-1.5 font-normal">Src</th>
                    <th id="segments-panel-th-target" className="px-2 py-1.5 font-normal">Target</th>
                    <th id="segments-panel-th-speed" className="px-2 py-1.5 font-normal">Speed</th>
                  </tr>
                </thead>
                <tbody>
                  {payload.slots.map((row) => {
                    const selected = row.id === selectedSlotId;
                    return (
                      <tr
                        id={`segments-panel-row-${row.id}`}
                        key={row.id}
                        className={
                          selected
                            ? "bg-scope-dim/10 text-scope-trace"
                            : "text-monitor-text"
                        }
                      >
                        <td id={`segments-panel-td-role-${row.id}`} className="px-2 py-1">{row.role}</td>
                        <td id={`segments-panel-td-src-${row.id}`} className="px-2 py-1 whitespace-nowrap">
                          {row.src_start_s.toFixed(2)}→{row.src_end_s.toFixed(2)}
                          <span id={`segments-panel-td-src-span-${row.id}`} className="text-monitor-muted">
                            {" "}
                            ({row.src_span_s.toFixed(2)}s)
                          </span>
                        </td>
                        <td id={`segments-panel-td-target-${row.id}`} className="px-2 py-1 whitespace-nowrap">
                          {row.target_duration_s.toFixed(2)}s
                        </td>
                        <td id={`segments-panel-td-speed-${row.id}`} className="px-2 py-1 whitespace-nowrap">
                          {row.speed_factor.toFixed(2)}×
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {payload && payload.summary.hook_speed_s != null && (
            <p id="segments-panel-hook-summary" className="font-mono text-[10px] text-monitor-muted">
              Hook unified{" "}
              {payload.summary.unified_crop
                ? `${payload.summary.unified_crop[0].toFixed(2)}→${payload.summary.unified_crop[1].toFixed(2)}s`
                : "—"}
              {" · "}
              {payload.summary.hook_speed_s.toFixed(2)}× avg
            </p>
          )}
        </>
      )}
    </div>
  );
}
