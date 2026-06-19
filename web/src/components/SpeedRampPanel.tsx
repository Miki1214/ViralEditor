import { useEffect, useMemo, useState } from "react";
import {
  fetchSpeedRamp,
  speedProxyPreviewUrl,
  updateSpeedSelection,
} from "../api/client";
import type { SpeedRampOptionSet, WaveformPayload } from "../types";
import { SpeedCurveCanvas } from "./SpeedCurveCanvas";

interface SpeedRampPanelProps {
  jobId: string;
  waveform: WaveformPayload;
  outputDurationS: number;
}

export function SpeedRampPanel({
  jobId,
  waveform,
  outputDurationS: requestedOutputDurationS,
}: SpeedRampPanelProps) {
  const [optionSet, setOptionSet] = useState<SpeedRampOptionSet | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [updating, setUpdating] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [rendering, setRendering] = useState(false);
  const [previewNonce, setPreviewNonce] = useState(0);

  const [alpha, setAlpha] = useState(0);
  const [maxSpeed, setMaxSpeed] = useState(30);
  const [dropHoldMs, setDropHoldMs] = useState(300);
  const [bassAccent, setBassAccent] = useState(0.2);

  const loadOptions = () => {
    setLoading(true);
    fetchSpeedRamp(jobId)
      .then((payload) => {
        setOptionSet(payload);
        const selected = payload.options.find((item) => item.style === payload.selected_style);
        if (selected) {
          setAlpha(Math.round(selected.plan.max_speed > 0 ? selected.plan.avg_speed : 0));
        }
        setError(null);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : "Could not load speed options");
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    loadOptions();
  }, [jobId, requestedOutputDurationS]);

  const selected = useMemo(() => {
    if (!optionSet) return null;
    return (
      optionSet.options.find((item) => item.style === optionSet.selected_style) ??
      optionSet.options[0] ??
      null
    );
  }, [optionSet]);

  const handleSelectStyle = async (style: string) => {
    if (!optionSet || updating) return;
    setUpdating(true);
    try {
      const next = await updateSpeedSelection(jobId, { style });
      setOptionSet(next);
      setPreviewNonce((value) => value + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update speed profile");
    } finally {
      setUpdating(false);
    }
  };

  const laneDurationS = selected?.plan.output_duration_s ?? requestedOutputDurationS;
  const durationCapped =
    selected?.plan.requested_output_duration_s != null &&
    selected.plan.requested_output_duration_s > selected.plan.output_duration_s + 0.01;

  const handleApplyAdvanced = async () => {
    if (!optionSet || updating) return;
    setUpdating(true);
    try {
      const next = await updateSpeedSelection(jobId, {
        style: optionSet.selected_style,
        alpha,
        s_max: maxSpeed,
        drop_window_ms: dropHoldMs,
        bass_accent: bassAccent,
      });
      setOptionSet(next);
      setPreviewNonce((value) => value + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not apply tuning");
    } finally {
      setUpdating(false);
    }
  };

  const handleRenderPreview = () => {
    setRendering(true);
    setPreviewNonce((value) => value + 1);
    window.setTimeout(() => setRendering(false), 400);
  };

  const previewUrl =
    selected && previewNonce > 0
      ? `${speedProxyPreviewUrl(jobId, selected.style)}&_=${previewNonce}`
      : null;

  if (loading) {
    return (
      <div className="panel p-4">
        <p className="font-mono text-xs uppercase tracking-[0.2em] text-monitor-muted">
          Loading velocity lane…
        </p>
      </div>
    );
  }

  if (error && !optionSet) {
    return (
      <div className="panel p-4">
        <p className="text-sm text-hook-gold">{error}</p>
        <button type="button" className="btn-ghost mt-3 text-xs" onClick={loadOptions}>
          Retry
        </button>
      </div>
    );
  }

  if (!optionSet || !selected) {
    return (
      <div className="panel p-4">
        <p className="text-sm text-monitor-muted">Pick a profile to see its velocity curve.</p>
      </div>
    );
  }

  return (
    <div className="panel space-y-4 p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-scope-trace">
            Velocity lane
          </p>
          <h2 className="text-sm font-semibold">Speed ramp profiles</h2>
        </div>
        <button
          type="button"
          className="btn-primary text-xs"
          disabled={rendering}
          onClick={handleRenderPreview}
        >
          {rendering ? "Rendering…" : "Render preview"}
        </button>
      </div>

      <div className="overflow-x-auto">
        <div className="flex min-w-[320px] gap-2">
          {optionSet.options.map((option) => {
            const active = option.style === optionSet.selected_style;
            return (
              <button
                key={option.style}
                type="button"
                onClick={() => handleSelectStyle(option.style)}
                disabled={updating}
                className={`min-w-[140px] flex-1 rounded border px-3 py-3 text-left transition ${
                  active
                    ? "border-scope-trace bg-scope-trace/10"
                    : "border-monitor-border bg-monitor-bg hover:border-scope-dim"
                }`}
              >
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-monitor-muted">
                  {option.label}
                </p>
                <p className="mt-1 font-mono text-2xl font-bold text-scope-trace">
                  {option.plan.avg_speed.toFixed(1)}x
                </p>
                <p className="font-mono text-[10px] text-monitor-muted">
                  PEAK {option.plan.max_speed.toFixed(1)}x · SLOW {option.plan.slow_zone_count}
                </p>
                <p className="mt-2 text-xs text-monitor-muted">{option.description}</p>
              </button>
            );
          })}
        </div>
      </div>

      {durationCapped && (
        <p className="rounded border border-hook-gold/30 bg-hook-gold/10 px-3 py-2 text-xs text-hook-gold">
          Music window is longer than your source video. Speed ramp is capped to{" "}
          <span className="font-mono">{selected.plan.output_duration_s.toFixed(1)}s</span> (source
          length) — the clip will not be looped or stretched.
        </p>
      )}

      <div className="overflow-x-auto">
        <SpeedCurveCanvas
          durationS={laneDurationS}
          curve={selected.plan.speed_curve}
          sections={waveform.sections}
          downbeats={waveform.downbeats}
          minSpeed={selected.plan.min_speed}
          maxSpeed={selected.plan.max_speed}
          animateKey={`${selected.style}-${previewNonce}`}
        />
      </div>

      <details
        open={advancedOpen}
        onToggle={(event) => setAdvancedOpen((event.target as HTMLDetailsElement).open)}
        className="rounded border border-monitor-border bg-monitor-bg px-3 py-2"
      >
        <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
          Advanced tuning
        </summary>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="field-label">Intensity (alpha)</span>
            <input
              type="range"
              min={0}
              max={30}
              step={0.5}
              value={alpha}
              onChange={(event) => setAlpha(Number(event.target.value))}
              className="w-full accent-scope-trace"
            />
            <span className="font-mono text-xs text-scope-trace">{alpha.toFixed(1)}</span>
          </label>
          <label className="block">
            <span className="field-label">Max speed</span>
            <input
              type="range"
              min={5}
              max={40}
              step={0.5}
              value={maxSpeed}
              onChange={(event) => setMaxSpeed(Number(event.target.value))}
              className="w-full accent-scope-trace"
            />
            <span className="font-mono text-xs text-scope-trace">{maxSpeed.toFixed(1)}x</span>
          </label>
          <label className="block">
            <span className="field-label">Drop hold (ms)</span>
            <input
              type="range"
              min={100}
              max={800}
              step={10}
              value={dropHoldMs}
              onChange={(event) => setDropHoldMs(Number(event.target.value))}
              className="w-full accent-scope-trace"
            />
            <span className="font-mono text-xs text-scope-trace">{dropHoldMs} ms</span>
          </label>
          <label className="block">
            <span className="field-label">Bass accent</span>
            <input
              type="range"
              min={0}
              max={1}
              step={0.05}
              value={bassAccent}
              onChange={(event) => setBassAccent(Number(event.target.value))}
              className="w-full accent-scope-trace"
            />
            <span className="font-mono text-xs text-scope-trace">{bassAccent.toFixed(2)}</span>
          </label>
        </div>
        <button
          type="button"
          className="btn-ghost mt-3 text-xs"
          disabled={updating}
          onClick={handleApplyAdvanced}
        >
          Apply tuning
        </button>
      </details>

      {previewUrl && (
        <div className="overflow-hidden rounded border border-monitor-border bg-monitor-bg">
          <video
            key={previewUrl}
            src={previewUrl}
            controls
            playsInline
            className="mx-auto max-h-[360px] w-full bg-black"
          />
        </div>
      )}

      {error && <p className="text-sm text-hook-gold">{error}</p>}
    </div>
  );
}
