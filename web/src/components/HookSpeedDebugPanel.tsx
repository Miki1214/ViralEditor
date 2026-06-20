import { useEffect, useMemo, useState } from "react";
import { fetchStoryboardSegments } from "../api/client";
import type { StoryboardPayload, StoryboardSegmentsDebugPayload } from "../types";
import { hookUnifiedLabelSpeed, isHookFamilyRole } from "../utils/hookCrop";

const MISMATCH_EPSILON = 0.02;

interface HookSpeedDebugPanelProps {
  jobId: string;
  storyboard: StoryboardPayload;
  /** Local crop slider values before/at commit — refreshes segment preview. */
  pendingCropKey?: string;
}

function localLabelSpeed(
  storyboard: StoryboardPayload,
  role: StoryboardSegmentsDebugPayload["slots"][number]["role"],
  slotId: string,
): number | null {
  const slot = storyboard.slots.find((entry) => entry.id === slotId);
  if (!slot) {
    return null;
  }
  if (isHookFamilyRole(role)) {
    return hookUnifiedLabelSpeed(storyboard, slot);
  }
  const start = slot.crop_start_s ?? 0;
  const end = slot.crop_end_s ?? slot.target_duration_s;
  const span = Math.max(end - start, 0);
  if (span <= 0 || slot.target_duration_s <= 0) {
    return null;
  }
  return span / slot.target_duration_s;
}

export function HookSpeedDebugPanel({
  jobId,
  storyboard,
  pendingCropKey = "",
}: HookSpeedDebugPanelProps) {
  const [open, setOpen] = useState(true);
  const [payload, setPayload] = useState<StoryboardSegmentsDebugPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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
    let cancelled = false;
    setLoading(true);
    setError(null);
    void fetchStoryboardSegments(jobId)
      .then((data) => {
        if (cancelled) return;
        setPayload(data);
        console.info("[hook-speed-debug] segments", data);
      })
      .catch((err: unknown) => {
        if (cancelled) return;
        const message = err instanceof Error ? err.message : String(err);
        setError(message);
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
  }, [jobId, storyboardKey, pendingCropKey]);

  if (!open) {
    return (
      <button
        type="button"
        className="font-mono text-[10px] text-scope-dim hover:text-monitor-text"
        onClick={() => setOpen(true)}
      >
        Show hook speed debug
      </button>
    );
  }

  return (
    <div className="rounded border border-amber-700/50 bg-amber-950/20 p-3 space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="font-mono text-[10px] uppercase text-amber-400/90">Hook speed debug</p>
        <button
          type="button"
          className="font-mono text-[10px] text-monitor-muted hover:text-monitor-text"
          onClick={() => setOpen(false)}
        >
          Hide
        </button>
      </div>
      {loading && (
        <p className="font-mono text-[10px] text-monitor-muted">Loading segment table…</p>
      )}
      {error && (
        <p className="font-mono text-[10px] text-red-400">{error}</p>
      )}
      {payload && (
        <>
          <p className="font-mono text-[10px] text-monitor-muted">
            unified crop{" "}
            {payload.summary.unified_crop
              ? `${payload.summary.unified_crop[0].toFixed(2)}→${payload.summary.unified_crop[1].toFixed(2)}s`
              : "—"}
            {" · "}
            hook budget {payload.summary.hook_budget_s.toFixed(2)}s
            {" · "}
            label speed{" "}
            {payload.summary.hook_speed_s != null
              ? `${payload.summary.hook_speed_s.toFixed(2)}×`
              : "—"}
          </p>
          <div className="overflow-x-auto">
            <table className="w-full font-mono text-[10px]">
              <thead>
                <tr className="text-left text-monitor-muted">
                  <th className="pr-2 py-1">role</th>
                  <th className="pr-2 py-1">src</th>
                  <th className="pr-2 py-1">target</th>
                  <th className="pr-2 py-1">speed</th>
                  <th className="pr-2 py-1">label</th>
                  <th className="py-1">Δ</th>
                </tr>
              </thead>
              <tbody>
                {payload.slots.map((row) => {
                  const label = localLabelSpeed(storyboard, row.role, row.id);
                  const delta =
                    label != null ? Math.abs(label - row.speed_factor) : null;
                  const mismatch = delta != null && delta > MISMATCH_EPSILON;
                  return (
                    <tr
                      key={row.id}
                      className={mismatch ? "text-red-400" : "text-monitor-text"}
                    >
                      <td className="pr-2 py-0.5">{row.role}</td>
                      <td className="pr-2 py-0.5">
                        {row.src_start_s.toFixed(2)}→{row.src_end_s.toFixed(2)}
                        <span className="text-monitor-muted"> ({row.src_span_s.toFixed(2)}s)</span>
                      </td>
                      <td className="pr-2 py-0.5">{row.target_duration_s.toFixed(2)}s</td>
                      <td className="pr-2 py-0.5">{row.speed_factor.toFixed(2)}×</td>
                      <td className="pr-2 py-0.5">
                        {label != null ? `${label.toFixed(2)}×` : "—"}
                      </td>
                      <td className="py-0.5">
                        {delta != null ? (
                          mismatch ? (
                            <span title="label vs composite speed mismatch">
                              {delta.toFixed(3)} ⚠
                            </span>
                          ) : (
                            delta.toFixed(3)
                          )
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
