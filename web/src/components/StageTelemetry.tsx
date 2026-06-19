import { useEffect, useState } from "react";
import type { JobSummary, PipelineEvent, StageInfo } from "../types";

interface StageTelemetryProps {
  stages: StageInfo[];
  events: PipelineEvent[];
  status: JobSummary["status"] | null;
  hasOutput?: boolean;
}

function stageState(
  stageId: string,
  events: PipelineEvent[],
): "idle" | "active" | "done" | "skipped" | "error" {
  const stageEvents = events.filter((e) => e.stage === stageId);
  if (stageEvents.some((e) => e.action === "error")) return "error";
  if (stageEvents.some((e) => e.action === "complete")) return "done";
  if (stageEvents.some((e) => e.action === "skip")) return "skipped";
  if (stageEvents.some((e) => e.action === "start")) return "active";
  return "idle";
}

const stateStyles: Record<string, string> = {
  idle: "border-monitor-border/80 bg-monitor-bg/50 text-monitor-muted",
  active: "border-scope-trace bg-scope-trace/10 text-scope-trace animate-pulse-scope",
  done: "border-scope-dim/80 bg-scope-dim/10 text-scope-trace",
  skipped: "border-monitor-border/60 bg-monitor-bg/30 text-monitor-muted line-through decoration-monitor-muted",
  error: "border-hook-gold/70 bg-hook-gold/10 text-hook-gold",
};

const stateLabels: Record<string, string> = {
  idle: "idle",
  active: "running",
  done: "done",
  skipped: "skip",
  error: "error",
};

export function StageTelemetry({ stages, events, status, hasOutput = false }: StageTelemetryProps) {
  const statusLabel =
    status === "completed" && !hasOutput ? "analysis done" : status ?? "";
  const [logsOpen, setLogsOpen] = useState(false);

  useEffect(() => {
    if (status === "running") {
      setLogsOpen(true);
    }
  }, [status]);

  return (
    <div className="space-y-3">
      <div className="flex min-w-0 items-center gap-4">
        <div className="flex shrink-0 items-center gap-2">
          <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Pipeline
          </h2>
          {statusLabel && (
            <span className="rounded border border-scope-dim/50 bg-scope-dim/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-scope-trace">
              {statusLabel}
            </span>
          )}
        </div>

        <div className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto pb-0.5">
          {stages.map((stage, index) => {
            const state = stageState(stage.id, events);
            const last = [...events].reverse().find((e) => e.stage === stage.id);
            const tooltip = last?.message
              ? `${stage.label}: ${stateLabels[state]} — ${last.message}`
              : `${stage.label}: ${stateLabels[state]}`;

            return (
              <div key={stage.id} className="flex shrink-0 items-center gap-1">
                {index > 0 && (
                  <span className="select-none px-0.5 font-mono text-[10px] text-monitor-muted/35">
                    ›
                  </span>
                )}
                <div
                  title={tooltip}
                  className={`flex items-center gap-1.5 whitespace-nowrap rounded border px-2.5 py-1 font-mono text-[11px] ${stateStyles[state]}`}
                >
                  <span>{stage.label}</span>
                  <span className="text-[9px] uppercase tracking-wide opacity-75">
                    {stateLabels[state]}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {events.length > 0 && (
        <div className="rounded border border-monitor-border bg-monitor-bg">
          <button
            type="button"
            className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition hover:bg-monitor-surface/50"
            aria-expanded={logsOpen}
            onClick={() => setLogsOpen((open) => !open)}
          >
            <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
              Event log
            </span>
            <span className="flex items-center gap-2 font-mono text-[10px] text-monitor-muted">
              <span>{events.length}</span>
              <span
                className={`inline-block transition-transform ${logsOpen ? "rotate-180" : ""}`}
                aria-hidden
              >
                ▾
              </span>
            </span>
          </button>
          {logsOpen && (
            <div className="max-h-48 overflow-y-auto border-t border-monitor-border p-2 font-mono text-[10px] leading-relaxed text-monitor-muted">
              {events.map((event, index) => (
                <p key={`${event.timestamp}-${index}`}>
                  <span className="text-scope-trace">{event.stage}</span>
                  {" · "}
                  {event.action}
                  {event.message ? ` — ${event.message}` : ""}
                </p>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
