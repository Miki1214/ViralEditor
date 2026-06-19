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
    <div className="panel p-5">
      <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
        Output
      </h2>

      {status === "failed" && (
        <p className="mt-3 text-sm text-hook-gold">
          Render failed. Check pipeline telemetry for details.
        </p>
      )}

      {hasOutput ? (
        <div className="mt-4 space-y-3">
          <video
            className="w-full max-w-sm rounded-lg border border-monitor-border"
            controls
            src={outputUrl(jobId)}
          />
          <a className="btn-ghost inline-flex" href={outputUrl(jobId)} download="result.mp4">
            Download MP4
          </a>
        </div>
      ) : analysisDone ? (
        <div className="mt-3 space-y-3 text-sm text-monitor-muted">
          <p>
            Audio analysis is ready — pick a music block in the scope above, then run again when
            encode is available.
          </p>
          {artifacts.length > 0 && (
            <div>
              <p className="font-mono text-[10px] uppercase tracking-wider text-scope-trace">
                Artifacts written
              </p>
              <ul className="mt-2 space-y-1 font-mono text-xs">
                {artifacts.map((name) => (
                  <li key={name} className="rounded border border-monitor-border bg-monitor-bg px-2 py-1">
                    temp/{name}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : status === "running" ? (
        <p className="mt-3 text-sm text-monitor-muted">Pipeline running…</p>
      ) : null}
    </div>
  );
}
