import type { JobSummary, PipelineEvent, StageInfo } from "../types";

interface StageTelemetryProps {
  stages: StageInfo[];
  events: PipelineEvent[];
  status: JobSummary["status"] | null;
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
  idle: "border-monitor-border text-monitor-muted",
  active: "border-scope-trace text-scope-trace animate-pulse-scope",
  done: "border-scope-dim text-scope-trace",
  skipped: "border-monitor-border text-monitor-muted line-through decoration-monitor-muted",
  error: "border-hook-gold text-hook-gold",
};

export function StageTelemetry({ stages, events, status }: StageTelemetryProps) {
  return (
    <div className="panel p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
          Pipeline telemetry
        </h2>
        {status && (
          <span className="font-mono text-[10px] uppercase tracking-wider text-scope-trace">
            {status}
          </span>
        )}
      </div>

      <ol className="space-y-2">
        {stages.map((stage) => {
          const state = stageState(stage.id, events);
          const last = [...events].reverse().find((e) => e.stage === stage.id);
          return (
            <li
              key={stage.id}
              className={`flex items-start justify-between gap-3 rounded border bg-monitor-bg px-3 py-2 font-mono text-xs ${stateStyles[state]}`}
            >
              <span>{stage.label}</span>
              <span className="text-right text-[10px] uppercase tracking-wide opacity-80">
                {state}
              </span>
              {last?.message && (
                <span className="col-span-2 hidden text-[10px] text-monitor-muted sm:block">
                  {last.message}
                </span>
              )}
            </li>
          );
        })}
      </ol>

      {events.length > 0 && (
        <div className="mt-4 max-h-48 overflow-y-auto rounded border border-monitor-border bg-monitor-bg p-2 font-mono text-[10px] leading-relaxed text-monitor-muted">
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
  );
}
