import { outputUrl } from "../api/client";
import type { JobSummary } from "../types";

interface OutputPanelProps {
  jobId: string | null;
  status: JobSummary["status"] | null;
  hasOutput: boolean;
  artifacts: string[];
  scopeReady?: boolean;
  renderReady?: boolean;
  rendering?: boolean;
  renderProgress?: number | null;
  outputVersion?: number;
  onRender?: () => void;
  renderBlockedReason?: string | null;
}

export function OutputPanel({
  jobId,
  status,
  hasOutput,
  artifacts,
  scopeReady = false,
  renderReady = false,
  rendering = false,
  renderProgress = null,
  outputVersion = 0,
  onRender,
  renderBlockedReason,
}: OutputPanelProps) {
  if (!jobId) return null;

  const canRender = renderReady && onRender != null && !rendering;
  const showFirstRenderCta = canRender && !hasOutput;
  const videoSrc = outputUrl(jobId, outputVersion);
  const analysisDone = status === "completed" && !hasOutput && !rendering;

  return (
    <div id="output-panel" className="panel p-5">
      <h2 id="output-panel-title" className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
        Final output
      </h2>

      {status === "failed" && !rendering && (
        <p id="output-panel-failed-msg" className="mt-3 text-sm text-hook-gold">
          Render failed. Check pipeline telemetry for details.
        </p>
      )}

      {rendering ? (
        <div id="output-panel-render-progress" className="mt-4 space-y-3">
          <p className="text-sm text-monitor-muted">
            {hasOutput ? "Re-encoding final video with your latest changes…" : "Encoding final 1080×1920 video…"}
          </p>
          <div className="render-progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={renderProgress ?? undefined}>
            {renderProgress != null ? (
              <div
                className="h-full rounded-full bg-scope-trace transition-[width] duration-300 ease-out"
                style={{ width: `${Math.min(100, Math.max(0, renderProgress))}%` }}
              />
            ) : (
              <div className="render-progress-bar" />
            )}
          </div>
          {renderProgress != null && (
            <p className="font-mono text-[10px] text-monitor-muted">
              {Math.round(renderProgress)}% encoded
              {renderProgress < 100 ? " — FFmpeg encode in progress" : ""}
            </p>
          )}
          {hasOutput && (
            <video
              id="output-panel-video-stale"
              className="monitor-video w-full max-w-sm rounded-lg border border-monitor-border opacity-40"
              controls={false}
              muted
              src={videoSrc}
            />
          )}
        </div>
      ) : hasOutput ? (
        <div className="mt-4 space-y-3">
          <video
            id="output-panel-video"
            key={videoSrc}
            className="monitor-video w-full max-w-sm rounded-lg border border-monitor-border"
            controls
            src={videoSrc}
          />
          <div className="flex flex-wrap items-center gap-2">
            <a
              id="output-panel-download-btn"
              className="btn-ghost inline-flex"
              href={videoSrc}
              download="result.mp4"
            >
              Download MP4
            </a>
            {canRender && (
              <button
                id="output-panel-rerender-btn"
                type="button"
                className="btn-primary px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
                onClick={onRender}
                disabled={Boolean(renderBlockedReason)}
              >
                Re-render video
              </button>
            )}
          </div>
          {canRender && (
            <p className="text-xs text-monitor-muted">
              Storyboard or FX changed? Re-render to bake updates into the final MP4.
            </p>
          )}
          {renderBlockedReason && (
            <p className="text-xs text-hook-gold">{renderBlockedReason}</p>
          )}
        </div>
      ) : showFirstRenderCta ? (
        <div className="mt-4 space-y-3">
          <p className="text-sm text-monitor-muted">
            All storyboard slots are filled. Encode the final 1080×1920 / 60&nbsp;fps MP4.
          </p>
          <button
            id="output-panel-render-btn"
            type="button"
            className="btn-primary px-4 py-2 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-50"
            onClick={onRender}
            disabled={Boolean(renderBlockedReason)}
          >
            Render final video
          </button>
          {renderBlockedReason && (
            <p className="text-xs text-hook-gold">{renderBlockedReason}</p>
          )}
        </div>
      ) : status === "failed" && canRender ? (
        <div className="mt-4 space-y-3">
          <button
            id="output-panel-retry-render-btn"
            type="button"
            className="btn-primary px-4 py-2 text-sm font-medium"
            onClick={onRender}
            disabled={Boolean(renderBlockedReason)}
          >
            Retry render
          </button>
        </div>
      ) : analysisDone && scopeReady ? (
        <div className="mt-3 space-y-3 text-sm text-monitor-muted">
          <p id="output-panel-analysis-msg">
            Assign a clip to every storyboard slot to unlock final render.
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
        <p id="output-panel-pipeline-msg" className="mt-3 text-sm text-monitor-muted">
          Pipeline running…
        </p>
      ) : null}
    </div>
  );
}
