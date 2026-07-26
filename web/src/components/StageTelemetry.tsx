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

function formatElapsedMs(ms: number): string {
  const safe = Math.max(0, ms);
  if (safe < 1000) {
    return `${Math.round(safe)}ms`;
  }
  if (safe < 60_000) {
    return `${(safe / 1000).toFixed(2)}s`;
  }
  const minutes = Math.floor(safe / 60_000);
  const seconds = (safe % 60_000) / 1000;
  return `${minutes}m ${seconds.toFixed(1)}s`;
}

function formatLogOffsetMs(ms: number): string {
  const safe = Math.max(0, ms);
  if (safe < 60_000) {
    return `+${(safe / 1000).toFixed(2)}s`;
  }
  const minutes = Math.floor(safe / 60_000);
  const seconds = ((safe % 60_000) / 1000).toFixed(1);
  return `+${minutes}m ${seconds}s`;
}

interface EnrichedEvent {
  event: PipelineEvent;
  offsetMs: number;
  stageDurationMs: number | null;
}

function enrichEvents(events: PipelineEvent[]): EnrichedEvent[] {
  const jobStart = events.find((event) => event.timestamp > 0)?.timestamp ?? 0;
  const stageStarts = new Map<string, number>();

  return events.map((event) => {
    const offsetMs = jobStart > 0 ? (event.timestamp - jobStart) * 1000 : 0;
    let stageDurationMs: number | null = null;

    if (event.action === "start") {
      stageStarts.set(event.stage, event.timestamp);
    } else if (
      event.action === "complete" ||
      event.action === "error" ||
      event.action === "skip"
    ) {
      const stageStart = stageStarts.get(event.stage);
      if (stageStart != null && event.timestamp >= stageStart) {
        stageDurationMs = (event.timestamp - stageStart) * 1000;
      }
    }

    return { event, offsetMs, stageDurationMs };
  });
}

function stageDurationMs(stageId: string, events: PipelineEvent[]): number | null {
  const stageEvents = events.filter((event) => event.stage === stageId);
  const start = stageEvents.find((event) => event.action === "start");
  const end = [...stageEvents]
    .reverse()
    .find(
      (event) =>
        event.action === "complete" || event.action === "error" || event.action === "skip",
    );
  if (!start || !end || end.timestamp < start.timestamp) {
    return null;
  }
  return (end.timestamp - start.timestamp) * 1000;
}

function latestStageInfo(events: PipelineEvent[], stageId: string): string | null {
  for (let index = events.length - 1; index >= 0; index -= 1) {
    const event = events[index];
    if (event.stage === stageId && event.action === "info" && event.message) {
      return event.message;
    }
  }
  return null;
}

function formatEventAction(action: PipelineEvent["action"]): string {
  if (action === "info") {
    return "…";
  }
  return action;
}

export function StageTelemetry({ stages, events, status, hasOutput = false }: StageTelemetryProps) {
  const statusLabel =
    status === "completed" && !hasOutput ? "analysis done" : status ?? "";
  const [logsOpen, setLogsOpen] = useState(false);

  useEffect(() => {
    if (status === "running") {
      setLogsOpen(true);
    }
  }, [status]);

  const enrichedEvents = enrichEvents(events);

  return (
    <div id="stage-telemetry-container" className="space-y-3">
      <div className="flex min-w-0 items-center gap-4">
        <div className="flex shrink-0 items-center gap-2">
          <h2 id="stage-telemetry-title" className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Pipeline
          </h2>
          {statusLabel && (
            <span id="stage-telemetry-status" className="rounded border border-scope-dim/50 bg-scope-dim/10 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wider text-scope-trace">
              {statusLabel}
            </span>
          )}
        </div>

        <div id="stage-telemetry-stages" className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto pb-0.5">
          {stages.map((stage, index) => {
            const state = stageState(stage.id, events);
            const last = [...events].reverse().find((e) => e.stage === stage.id);
            const activeStep = state === "active" ? latestStageInfo(events, stage.id) : null;
            const duration = stageDurationMs(stage.id, events);
            const durationHint =
              duration != null && state !== "active" ? ` · ${formatElapsedMs(duration)}` : "";
            const tooltip = activeStep
              ? `${stage.label}: ${activeStep}`
              : last?.message
                ? `${stage.label}: ${stateLabels[state]}${durationHint} — ${last.message}`
                : `${stage.label}: ${stateLabels[state]}${durationHint}`;

            return (
              <div id={`stage-telemetry-stage-${stage.id}`} key={stage.id} className="flex shrink-0 items-center gap-1">
                {index > 0 && (
                  <span className="select-none px-0.5 font-mono text-[10px] text-monitor-muted/35">
                    ›
                  </span>
                )}
                <div
                  title={tooltip}
                  className={`flex max-w-[11rem] flex-col gap-0.5 rounded border px-2.5 py-1 font-mono text-[11px] ${stateStyles[state]}`}
                >
                  <div className="flex items-center gap-1.5 whitespace-nowrap">
                    <span id={`stage-telemetry-state-${stage.id}`}>{stage.label}</span>
                    <span id={`stage-telemetry-active-${stage.id}`} className="text-[9px] uppercase tracking-wide opacity-75">
                      {stateLabels[state]}
                    </span>
                  </div>
                  {activeStep && (
                    <span className="truncate text-[9px] normal-case tracking-normal opacity-80">
                      {activeStep}
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {events.length > 0 && (
        <div className="rounded border border-monitor-border bg-monitor-bg">
          <button
            id="stage-telemetry-log-toggle"
            type="button"
            className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left transition hover:bg-monitor-surface/50"
            aria-expanded={logsOpen}
            onClick={() => setLogsOpen((open) => !open)}
          >
            <span id="stage-telemetry-log-count" className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
              Event log
            </span>
            <span className="flex items-center gap-2 font-mono text-[10px] text-monitor-muted">
              <span>{events.length}</span>
              <span id="stage-telemetry-chevron"
                className={`inline-block transition-transform ${logsOpen ? "rotate-180" : ""}`}
                aria-hidden
              >
                ▾
              </span>
            </span>
          </button>
          {logsOpen && (
            <div id="stage-telemetry-log-panel" className="max-h-56 overflow-y-auto border-t border-monitor-border p-2 font-mono text-[10px] leading-relaxed text-monitor-muted">
              {enrichedEvents.map(({ event, offsetMs, stageDurationMs: durationMs }, index) => {
                const isInfo = event.action === "info";
                return (
                  <p
                    id={`stage-telemetry-log-${index}`}
                    key={`${event.timestamp}-${index}`}
                    className={`flex gap-2 ${isInfo ? "text-monitor-muted/90" : ""}`}
                  >
                    <span id={`stage-telemetry-offset-${index}`} className="w-[4.5rem] shrink-0 tabular-nums text-monitor-muted/70">
                      {event.timestamp > 0 ? formatLogOffsetMs(offsetMs) : "—"}
                    </span>
                    <span className="min-w-0">
                      <span id={`stage-telemetry-stage-name-${index}`} className={isInfo ? "text-monitor-muted" : "text-scope-trace"}>
                        {event.stage}
                      </span>
                      {" · "}
                      <span id={`stage-telemetry-action-${index}`} className={isInfo ? "text-monitor-muted/70" : ""}>
                        {formatEventAction(event.action)}
                      </span>
                      {!isInfo && durationMs != null && (
                        <>
                          {" · "}
                          <span id={`stage-telemetry-duration-${index}`} className="text-scope-dim">{formatElapsedMs(durationMs)}</span>
                        </>
                      )}
                      {event.message ? (
                        <>
                          {isInfo ? " " : " — "}
                          <span id={`stage-telemetry-message-${index}`} className={isInfo ? "text-monitor-text/85" : ""}>
                            {event.message}
                          </span>
                        </>
                      ) : (
                        ""
                      )}
                    </span>
                  </p>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
