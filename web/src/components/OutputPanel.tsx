import { outputUrl } from "../api/client";
import type { JobSummary } from "../types";

interface OutputPanelProps {
  jobId: string | null;
  status: JobSummary["status"] | null;
}

export function OutputPanel({ jobId, status }: OutputPanelProps) {
  if (!jobId) return null;

  const ready = status === "completed";

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

      {ready ? (
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
      ) : status === "running" ? (
        <p className="mt-3 text-sm text-monitor-muted">
          Pipeline running… ingest completes before later stages land in Phase 2+.
        </p>
      ) : null}
    </div>
  );
}
