import { useEffect, useId, useState, type ReactNode } from "react";
import {
  CUSTOM_DURATION_MAX_S,
  CUSTOM_DURATION_MIN_S,
  DEFAULT_TARGET_DURATION_S,
  isPresetTargetDuration,
  TARGET_DURATION_PRESETS,
} from "../constants/durations";
import { HOOK_FONT_OPTIONS } from "../constants/fonts";

export type FormState = {
  hookText: string;
  emphasisWords: string;
  fillColor: string;
  emphasisColor: string;
  fontFamily: string;
  safePaddingPct: number;
  targetDurationS: number;
  useFullTrack: boolean;
};

interface JobFormProps {
  form: FormState;
  onPatch: (partial: Partial<FormState>) => void;
  onAudioSelected: (file: File) => void;
  onTargetDurationChange?: (targetDurationS: number) => void;
  audioName: string | null;
  analyzing: boolean;
  disabled?: boolean;
  disabledReason?: string | null;
  audioScope?: ReactNode;
}

function durationChipClass(active: boolean): string {
  return `rounded border px-2.5 py-1 font-mono text-xs transition ${
    active
      ? "border-hook-gold bg-hook-gold/15 text-hook-gold"
      : "border-monitor-border text-monitor-muted hover:border-scope-dim"
  }`;
}

export function JobForm({
  form,
  onPatch,
  onAudioSelected,
  onTargetDurationChange,
  audioName,
  analyzing,
  disabled = false,
  disabledReason = null,
  audioScope = null,
}: JobFormProps) {
  const audioInputId = useId();
  const [customDuration, setCustomDuration] = useState(false);
  const [customDraft, setCustomDraft] = useState<string | null>(null);

  useEffect(() => {
    if (isPresetTargetDuration(form.targetDurationS)) {
      setCustomDuration(false);
    }
  }, [form.targetDurationS]);

  const clampDuration = (seconds: number) =>
    Math.max(
      CUSTOM_DURATION_MIN_S,
      Math.min(CUSTOM_DURATION_MAX_S, seconds),
    );

  const requestTargetDuration = (seconds: number) => {
    const clamped = clampDuration(seconds);
    if (clamped === form.targetDurationS && !customDuration) return;
    onTargetDurationChange?.(clamped);
  };

  const commitCustomDuration = () => {
    const parsed = Number(customDraft ?? form.targetDurationS);
    setCustomDraft(null);
    requestTargetDuration(Number.isFinite(parsed) ? parsed : DEFAULT_TARGET_DURATION_S);
  };

  const isCustom =
    customDuration || !isPresetTargetDuration(form.targetDurationS);

  return (
    <form
      className="panel space-y-6 p-5"
      onSubmit={(e) => e.preventDefault()}
    >
      <section className="space-y-3">
        <div>
          <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Step 1 — Target length
          </h2>
          <p className="mt-1 text-xs text-monitor-muted">
            Pick how long the short should be before analyzing your track.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {TARGET_DURATION_PRESETS.map((preset) => (
            <button
              key={preset.value}
              type="button"
              disabled={disabled}
              className={durationChipClass(
                !isCustom && form.targetDurationS === preset.value,
              )}
              onClick={() => {
                setCustomDuration(false);
                setCustomDraft(null);
                requestTargetDuration(preset.value);
              }}
            >
              {preset.label}
              {preset.value === DEFAULT_TARGET_DURATION_S && (
                <span className="ml-1 text-[10px] font-normal opacity-60">
                  default
                </span>
              )}
            </button>
          ))}
          <button
            type="button"
            disabled={disabled}
            className={durationChipClass(isCustom)}
            onClick={() => setCustomDuration(true)}
          >
            Custom
          </button>
        </div>
        {isCustom && (
          <label className="block max-w-[140px]">
            <span className="field-label">Seconds</span>
            <input
              type="number"
              min={CUSTOM_DURATION_MIN_S}
              max={CUSTOM_DURATION_MAX_S}
              className="field-input mt-1"
              disabled={disabled}
              value={customDraft ?? String(form.targetDurationS)}
              onChange={(e) => setCustomDraft(e.target.value)}
              onBlur={commitCustomDuration}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  commitCustomDuration();
                }
              }}
            />
          </label>
        )}
      </section>

      <section className="space-y-3">
        <div>
          <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Step 2 — Music
          </h2>
          <p className="mt-1 text-xs text-monitor-muted">
            Drop your track — we analyze beats and suggest the best window for{" "}
            {form.targetDurationS}s.
          </p>
        </div>
        <label htmlFor={audioInputId} className="block">
          <div className="flex min-h-[72px] cursor-pointer flex-col items-center justify-center rounded border border-dashed border-monitor-border bg-monitor-bg/50 px-4 py-4 text-center transition hover:border-scope-dim">
            <input
              id={audioInputId}
              type="file"
              accept="audio/*"
              className="sr-only"
              disabled={disabled || analyzing}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onAudioSelected(file);
                e.target.value = "";
              }}
            />
            <span className="text-xs text-monitor-muted">
              {audioName ?? "Drop music here or click to browse"}
            </span>
            {analyzing && (
              <span className="mt-2 font-mono text-[11px] text-scope-trace">
                Analyzing audio…
              </span>
            )}
          </div>
        </label>
        {audioScope}
      </section>

      <section className="space-y-4">
        <div>
          <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Step 3 — Hook & overlay
          </h2>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block sm:col-span-2">
            <span className="field-label">Hook text</span>
            <input
              className="field-input mt-1"
              value={form.hookText}
              onChange={(e) => onPatch({ hookText: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="field-label">Emphasis words</span>
            <input
              className="field-input mt-1"
              value={form.emphasisWords}
              onChange={(e) => onPatch({ emphasisWords: e.target.value })}
              placeholder="30, days"
            />
          </label>
          <label className="block">
            <span className="field-label">Font</span>
            <select
              className="field-select mt-1"
              value={form.fontFamily}
              onChange={(e) => onPatch({ fontFamily: e.target.value })}
            >
              {HOOK_FONT_OPTIONS.map((font) => (
                <option key={font.value} value={font.value}>
                  {font.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="field-label">Fill color</span>
            <input
              type="color"
              className="field-color"
              value={form.fillColor}
              onChange={(e) => onPatch({ fillColor: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="field-label">Emphasis color</span>
            <input
              type="color"
              className="field-color"
              value={form.emphasisColor}
              onChange={(e) => onPatch({ emphasisColor: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="field-label">Safe padding %</span>
            <input
              type="number"
              min={0}
              max={50}
              className="field-input mt-1"
              value={form.safePaddingPct}
              onChange={(e) =>
                onPatch({ safePaddingPct: Number(e.target.value) || 10 })
              }
            />
          </label>
        </div>
      </section>

      {disabledReason && (
        <p className="text-xs text-hook-gold">{disabledReason}</p>
      )}
    </form>
  );
}
