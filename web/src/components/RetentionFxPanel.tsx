import { useMemo } from "react";
import type {
  SpatialFxSettings,
  StoryboardPayload,
  TeaserSettings,
  Transient,
  WaveformPayload,
} from "../types";

interface RetentionFxPanelProps {
  storyboard: StoryboardPayload;
  waveform: WaveformPayload | null;
  saving?: boolean;
  onPatch: (payload: {
    teaser?: Partial<TeaserSettings>;
    spatial_fx?: Partial<SpatialFxSettings>;
  }) => void | Promise<void>;
}

function countFxCandidates(
  transients: Transient[],
  musicStartS: number,
  musicEndS: number,
): { zoom: number; rotate: number } {
  let zoom = 0;
  let rotate = 0;
  for (const transient of transients) {
    const t = transient.timestamp_ms / 1000;
    if (t < musicStartS || t >= musicEndS) continue;
    if (transient.type === "drop") zoom += 1;
    if (transient.type === "bass") rotate += 1;
  }
  return { zoom, rotate };
}

function hookBudgetS(storyboard: StoryboardPayload): number {
  const hook = storyboard.slots.find((slot) => slot.role === "hook");
  if (hook) return hook.target_duration_s;
  const start = storyboard.slots.find((slot) => slot.role === "hook_start");
  const end = storyboard.slots.find((slot) => slot.role === "hook_end");
  return (start?.target_duration_s ?? 0) + (end?.target_duration_s ?? 0);
}

function Toggle({
  checked,
  disabled,
  label,
  hint,
  onChange,
}: {
  checked: boolean;
  disabled?: boolean;
  label: string;
  hint: string;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-3">
      <span>
        <span className="block font-mono text-[11px] text-monitor-text">{label}</span>
        <span className="mt-0.5 block text-[10px] leading-snug text-monitor-muted">{hint}</span>
      </span>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        className={`relative mt-0.5 h-5 w-9 shrink-0 rounded-full transition ${
          checked ? "bg-scope-trace" : "bg-monitor-border"
        } disabled:opacity-40`}
        onClick={() => onChange(!checked)}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-full bg-monitor-bg shadow transition ${
            checked ? "left-[18px]" : "left-0.5"
          }`}
        />
      </button>
    </label>
  );
}

export function RetentionFxPanel({
  storyboard,
  waveform,
  saving = false,
  onPatch,
}: RetentionFxPanelProps) {
  const { teaser, spatial_fx: spatialFx } = storyboard;
  const hookBudget = useMemo(() => hookBudgetS(storyboard), [storyboard.slots]);
  const payoffS = Math.min(
    teaser.duration_s,
    Math.max(0.5, hookBudget - 0.25),
  );
  const buildupS = Math.max(hookBudget - payoffS, 0.25);
  const payoffShare = hookBudget > 0 ? payoffS / hookBudget : 0.5;
  const sourceSplitPct = Math.round(teaser.tail_fraction * 100);

  const fxCounts = useMemo(
    () =>
      waveform
        ? countFxCandidates(
            waveform.transients,
            storyboard.music_start_s,
            storyboard.music_end_s,
          )
        : { zoom: 0, rotate: 0 },
    [waveform, storyboard.music_start_s, storyboard.music_end_s],
  );

  const teaserPreviewLabel = teaser.enabled
    ? `${payoffS.toFixed(1)}s start · ${buildupS.toFixed(1)}s end · ${teaser.mask === "vignette" ? "vignette" : "dir blur"}`
    : "Off";

  return (
    <div className="rounded border border-monitor-border bg-monitor-bg/40 p-4 space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h3 className="font-mono text-[10px] uppercase tracking-[0.18em] text-monitor-muted">
            Retention FX
          </h3>
          <p className="mt-1 max-w-prose text-xs text-monitor-muted">
            Split the hook into start (payoff) and end (build-up) storyboard slots. The filmstrip
            and block scrubber follow the same order as the composite preview.
          </p>
        </div>
        <p className="font-mono text-[10px] text-scope-trace">{teaserPreviewLabel}</p>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="space-y-3 rounded border border-monitor-border/70 bg-monitor-surface/40 p-3">
          <Toggle
            checked={teaser.enabled}
            disabled={saving}
            label="Hook inversion"
            hint="Filmstrip: Hook · start → clips → Hook · end before loop."
            onChange={(enabled) => void onPatch({ teaser: { enabled } })}
          />
          <label className="block">
            <span className="field-label">Source split</span>
            <div className="mt-1 flex items-center gap-2 font-mono text-[10px] text-monitor-muted">
              <span className="w-4 text-scope-trace">1</span>
              <div className="relative flex-1">
                <div className="pointer-events-none absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-monitor-border" />
                <input
                  type="range"
                  min={1}
                  max={25}
                  step={1}
                  disabled={saving || !teaser.enabled}
                  value={sourceSplitPct}
                  className="relative z-[1] w-full"
                  onChange={(e) =>
                    void onPatch({
                      teaser: { tail_fraction: Number(e.target.value) / 100 },
                    })
                  }
                />
              </div>
              <span className="w-4 text-right text-scope-trace">2</span>
            </div>
            <p className="mt-1 font-mono text-[10px] text-monitor-muted">
              Tail slice {sourceSplitPct}% — part 2 is the payoff source; part 1 is build-up.
            </p>
          </label>
          <label className="block">
            <span className="field-label">Hook split</span>
            <div className="mt-1 flex items-center gap-2 font-mono text-[10px] text-monitor-muted">
              <span className="w-8 tabular-nums text-scope-trace">1 · {payoffS.toFixed(1)}s</span>
              <div className="relative flex-1">
                <div className="pointer-events-none absolute inset-x-0 top-1/2 h-px -translate-y-1/2 bg-monitor-border" />
                <input
                  type="range"
                  min={0.5}
                  max={Math.max(0.75, Math.min(4, hookBudget - 0.25))}
                  step={0.1}
                  disabled={saving || !teaser.enabled || hookBudget <= 0.75}
                  value={payoffS}
                  className="relative z-[1] w-full"
                  onChange={(e) =>
                    void onPatch({ teaser: { duration_s: Number(e.target.value) } })
                  }
                />
              </div>
              <span className="w-8 text-right tabular-nums text-scope-trace">
                2 · {buildupS.toFixed(1)}s
              </span>
            </div>
            <p className="mt-1 font-mono text-[10px] text-monitor-muted">
              Output timing — snapped to downbeats · {Math.round(payoffShare * 100)}% payoff ·{" "}
              {Math.round((1 - payoffShare) * 100)}% build-up ({hookBudget.toFixed(1)}s hook budget)
            </p>
          </label>
          <label className="block">
            <span className="field-label">Mask</span>
            <select
              className="field-select mt-1 w-full"
              disabled={saving || !teaser.enabled}
              value={teaser.mask}
              onChange={(e) =>
                void onPatch({
                  teaser: { mask: e.target.value as TeaserSettings["mask"] },
                })
              }
            >
              <option value="vignette">Vignette — soft dark edges</option>
              <option value="dir_blur">Directional blur — hide detail</option>
            </select>
          </label>
        </section>

        <section className="space-y-3 rounded border border-monitor-border/70 bg-monitor-surface/40 p-3">
          <Toggle
            checked={spatialFx.enabled}
            disabled={saving}
            label="Spatial FX"
            hint="Zoom punches on drops, rotation shakes on bass hits."
            onChange={(enabled) => void onPatch({ spatial_fx: { enabled } })}
          />
          <label className="block">
            <span className="field-label">Intensity</span>
            <div className="mt-1 flex items-center gap-2">
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                disabled={saving || !spatialFx.enabled}
                value={Math.round(spatialFx.intensity * 100)}
                className="flex-1"
                onChange={(e) =>
                  void onPatch({
                    spatial_fx: { intensity: Number(e.target.value) / 100 },
                  })
                }
              />
              <span className="w-10 font-mono text-[10px] tabular-nums text-scope-trace">
                {Math.round(spatialFx.intensity * 100)}%
              </span>
            </div>
          </label>
          <label className="block">
            <span className="field-label">Event density cap</span>
            <div className="mt-1 flex items-center gap-2">
              <input
                type="range"
                min={2}
                max={16}
                step={1}
                disabled={saving || !spatialFx.enabled}
                value={spatialFx.max_events_per_second}
                className="flex-1"
                onChange={(e) =>
                  void onPatch({
                    spatial_fx: { max_events_per_second: Number(e.target.value) },
                  })
                }
              />
              <span className="w-10 font-mono text-[10px] tabular-nums text-scope-trace">
                {spatialFx.max_events_per_second}/s
              </span>
            </div>
          </label>
          <p className="font-mono text-[10px] text-monitor-muted">
            {spatialFx.enabled ? (
              <>
                ~{fxCounts.zoom} zoom · ~{fxCounts.rotate} rotate in this music window
              </>
            ) : (
              "Enable to sync impulses to analyzed transients"
            )}
          </p>
        </section>
      </div>
    </div>
  );
}
