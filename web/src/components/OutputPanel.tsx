import { outputUrl } from "../api/client";
import type { JobSummary } from "../types";

interface OutputPanelProps {
  jobId: string | null;
  status: JobSummary["status"] | null;
  hasOutput: boolean;
  artifacts: string[];
  scopeReady?: boolean;
}

export function OutputPanel({
  jobId,
  status,
  hasOutput,
  artifacts,
  scopeReady = false,
}: OutputPanelProps) {
  if (!jobId) return null;

  const analysisDone = status === "completed" && !hasOutput;

  if (analysisDone && scopeReady) {
    return null;
  }

  return (
    <div id="output-panel" className="panel p-5">
      <h2 id="output-panel-title" className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
        Output
      </h2>

      {status === "failed" && (
        <p id="output-panel-failed-msg" className="mt-3 text-sm text-hook-gold">
          Render failed. Check pipeline telemetry for details.
        </p>
      )}

      {hasOutput ? (
        <div className="mt-4 space-y-3">
          <video
            id="output-panel-video"
            className="monitor-video w-full max-w-sm rounded-lg border border-monitor-border"
            controls
            src={outputUrl(jobId)}
          />
          <a id="output-panel-download-btn" className="btn-ghost inline-flex" href={outputUrl(jobId)} download="result.mp4">
            Download MP4
          </a>
        </div>
      ) : analysisDone ? (
        <div className="mt-3 space-y-3 text-sm text-monitor-muted">
          <p id="output-panel-analysis-msg">
            Audio analysis is ready — pick a music block in the scope above, then run again when
            encode is available.
          </p>
          {artifacts.length > 0 && (
            <div id="output-panel-artifacts">
              <p id="output-panel-artifacts-title" className="font-mono text-[10px] uppercase tracking-wider text-scope-trace">
                Artifacts written
              </p>
              <ul className="mt-2 space-y-1 font-mono text-xs">
                {artifacts.map((name) => (
                  <li id={`output-panel-artifact-${name}`} key={name} className="rounded border border-monitor-border bg-monitor-bg px-2 py-1">
                    temp/{name}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : status === "running" ? (
        <p id="output-panel-pipeline-msg" className="mt-3 text-sm text-monitor-muted">Pipeline running…</p>
      ) : null}
    </div>
  );
}
