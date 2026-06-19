import { useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import type {
  SpatialFxSettings,
  StoryboardPayload,
  TeaserSettings,
  Transient,
  WaveformPayload,
} from "../types";

const SLIDER_DEBOUNCE_MS = 400;

type EffectsPatchPayload = {
  teaser?: Partial<TeaserSettings>;
  spatial_fx?: Partial<SpatialFxSettings>;
};

function useDebouncedPatch(onPatch: (payload: EffectsPatchPayload) => void | Promise<void>) {
  const onPatchRef = useRef(onPatch);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  onPatchRef.current = onPatch;

  const cancel = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => cancel, [cancel]);

  const schedule = useCallback(
    (payload: EffectsPatchPayload) => {
      cancel();
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        void onPatchRef.current(payload);
      }, SLIDER_DEBOUNCE_MS);
    },
    [cancel],
  );

  return { schedule, cancel };
}

function useSliderDraft<T>(
  serverValue: T,
  { schedule, cancel }: ReturnType<typeof useDebouncedPatch>,
  toPayload: (value: T) => EffectsPatchPayload,
) {
  const [localValue, setLocalValue] = useState(serverValue);
  const localRef = useRef(serverValue);
  const toPayloadRef = useRef(toPayload);
  toPayloadRef.current = toPayload;

  useEffect(() => {
    localRef.current = serverValue;
    setLocalValue(serverValue);
  }, [serverValue]);

  const setValue = useCallback(
    (value: T) => {
      cancel();
      localRef.current = value;
      setLocalValue(value);
    },
    [cancel],
  );

  const commit = useCallback(() => {
    schedule(toPayloadRef.current(localRef.current));
  }, [schedule]);

  return { localValue, setValue, commit, cancelDrag: cancel };
}

function sliderReleaseHandlers(
  setValue: (value: number) => void,
  commit: () => void,
  cancelDrag: () => void,
) {
  return {
    onChange: (event: ChangeEvent<HTMLInputElement>) => {
      setValue(Number(event.target.value));
    },
    onPointerDown: () => cancelDrag(),
    onPointerUp: commit,
    onMouseUp: commit,
    onTouchEnd: commit,
    onKeyUp: commit,
  };
}

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

function nearestPayoffIndex(value: number, positions: number[]): number {
  if (positions.length === 0) return 0;
  let best = 0;
  let bestDist = Math.abs(positions[0] - value);
  for (let i = 1; i < positions.length; i += 1) {
    const dist = Math.abs(positions[i] - value);
    if (dist < bestDist) {
      best = i;
      bestDist = dist;
    }
  }
  return best;
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
  const debouncedPatch = useDebouncedPatch(onPatch);
  const hookBudget = useMemo(() => hookBudgetS(storyboard), [storyboard.slots]);
  const payoffDownbeats = useMemo(
    () => teaser.payoff_downbeats_s ?? [],
    [teaser.payoff_downbeats_s],
  );
  const serverPayoffS =
    payoffDownbeats.length > 0
      ? payoffDownbeats[nearestPayoffIndex(teaser.duration_s, payoffDownbeats)]
      : Math.min(teaser.duration_s, Math.max(0.5, hookBudget - 0.25));

  const sourceSplit = useSliderDraft(
    Math.round(teaser.tail_fraction * 100),
    debouncedPatch,
    (value) => ({ teaser: { tail_fraction: value / 100 } }),
  );
  const intensitySplit = useSliderDraft(
    Math.round(spatialFx.intensity * 100),
    debouncedPatch,
    (value) => ({ spatial_fx: { intensity: value / 100 } }),
  );
  const densitySplit = useSliderDraft(
    spatialFx.max_events_per_second,
    debouncedPatch,
    (value) => ({ spatial_fx: { max_events_per_second: value } }),
  );

  const sourceSplitPct = sourceSplit.localValue;
  const hookEndSlot = storyboard.slots.find((slot) => slot.role === "hook_end");
  const payoffS = serverPayoffS;
  const intensityPct = intensitySplit.localValue;
  const maxEventsPerSecond = densitySplit.localValue;

  const buildupFromSlots = hookEndSlot?.target_duration_s;
  const buildupS =
    buildupFromSlots != null && Math.abs(payoffS - serverPayoffS) < 0.05
      ? buildupFromSlots
      : Math.max(hookBudget - payoffS, 0.25);
  const payoffShare = hookBudget > 0 ? payoffS / hookBudget : 0.5;

  const payoffOptions = useMemo(
    () =>
      payoffDownbeats.map((payoff) => ({
        payoff,
        buildup: Math.max(hookBudget - payoff, 0.25),
      })),
    [payoffDownbeats, hookBudget],
  );

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
                  {...sliderReleaseHandlers(
                    sourceSplit.setValue,
                    sourceSplit.commit,
                    sourceSplit.cancelDrag,
                  )}
                />
              </div>
              <span className="w-4 text-right text-scope-trace">2</span>
            </div>
            <p className="mt-1 font-mono text-[10px] text-monitor-muted">
              Tail slice {sourceSplitPct}% — part 2 is the payoff source; part 1 is build-up.
            </p>
          </label>
          <fieldset
            className="block border-0 p-0 m-0 min-w-0"
            disabled={saving || !teaser.enabled}
          >
            <legend className="field-label">Hook split</legend>
            {payoffOptions.length === 0 ? (
              <p className="mt-1 font-mono text-[10px] text-monitor-muted">
                No downbeat positions in hook budget ({hookBudget.toFixed(1)}s)
              </p>
            ) : (
              <div
                className="mt-2 space-y-1"
                role="radiogroup"
                aria-label="Hook split downbeat positions"
              >
                {payoffOptions.map(({ payoff, buildup }) => {
                  const selected = Math.abs(serverPayoffS - payoff) < 0.05;
                  const singleOption = payoffOptions.length === 1;
                  return (
                    <label
                      key={payoff}
                      className={`flex cursor-pointer items-center gap-2 rounded border px-2 py-1.5 font-mono text-[10px] transition ${
                        selected
                          ? "border-scope-trace/60 bg-scope-trace/10 text-monitor-text"
                          : "border-monitor-border/60 text-monitor-muted hover:border-scope-dim"
                      } ${singleOption ? "cursor-default opacity-90" : ""}`}
                    >
                      <input
                        type="radio"
                        name="hook-split-payoff"
                        className="shrink-0 accent-[rgb(var(--scope-trace))]"
                        checked={selected}
                        disabled={singleOption}
                        onChange={() => void onPatch({ teaser: { duration_s: payoff } })}
                      />
                      <span className="tabular-nums text-scope-trace">1 · {payoff.toFixed(1)}s</span>
                      <span className="text-monitor-muted">→</span>
                      <span className="tabular-nums text-scope-trace">2 · {buildup.toFixed(1)}s</span>
                      {singleOption && (
                        <span className="ml-auto text-monitor-muted">only downbeat</span>
                      )}
                    </label>
                  );
                })}
              </div>
            )}
            <p className="mt-1 font-mono text-[10px] text-monitor-muted">
              {payoffOptions.length <= 1
                ? `Snapped to downbeat · ${Math.round(payoffShare * 100)}% payoff · ${Math.round((1 - payoffShare) * 100)}% build-up (${hookBudget.toFixed(1)}s hook budget)`
                : `${payoffOptions.length} downbeat positions · ${Math.round(payoffShare * 100)}% payoff · ${Math.round((1 - payoffShare) * 100)}% build-up (${hookBudget.toFixed(1)}s hook budget)`}
            </p>
          </fieldset>
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
                value={intensityPct}
                className="flex-1"
                {...sliderReleaseHandlers(
                  intensitySplit.setValue,
                  intensitySplit.commit,
                  intensitySplit.cancelDrag,
                )}
              />
              <span className="w-10 font-mono text-[10px] tabular-nums text-scope-trace">
                {intensityPct}%
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
                value={maxEventsPerSecond}
                className="flex-1"
                {...sliderReleaseHandlers(
                  densitySplit.setValue,
                  densitySplit.commit,
                  densitySplit.cancelDrag,
                )}
              />
              <span className="w-10 font-mono text-[10px] tabular-nums text-scope-trace">
                {maxEventsPerSecond}/s
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
