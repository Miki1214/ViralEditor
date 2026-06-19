import { useEffect, useMemo, useState } from "react";
import type { JobSummary, PipelineEvent, StageInfo } from "./types";
import {
  createJob,
  fetchArtifact,
  fetchHealth,
  fetchJobs,
  fetchStages,
  subscribeJobEvents,
} from "./api/client";
import { DEFAULT_HOOK_FONT } from "./constants/fonts";
import { JobForm } from "./components/JobForm";
import { OutputPanel } from "./components/OutputPanel";
import { PhonePreview } from "./components/PhonePreview";
import { StageTelemetry } from "./components/StageTelemetry";

type FormState = {
  hookText: string;
  emphasisWords: string;
  fillColor: string;
  emphasisColor: string;
  fontFamily: string;
  safePaddingPct: number;
  video: File | null;
  audio: File | null;
};

const initialForm: FormState = {
  hookText: "I built this in 30 days",
  emphasisWords: "30, days",
  fillColor: "#FFFFFF",
  emphasisColor: "#FFD700",
  fontFamily: DEFAULT_HOOK_FONT,
  safePaddingPct: 10,
  video: null,
  audio: null,
};

export default function App() {
  const [form, setForm] = useState<FormState>(initialForm);
  const [stages, setStages] = useState<StageInfo[]>([]);
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobSummary["status"] | null>(null);
  const [jobs, setJobs] = useState<JobSummary[]>([]);
  const [ffmpegOk, setFfmpegOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [mediaInfo, setMediaInfo] = useState<{
    outputDuration: number | null;
    videoFps: number | null;
    videoSize: string | null;
  }>({ outputDuration: null, videoFps: null, videoSize: null });

  const videoPreviewUrl = useMemo(() => {
    if (!form.video) return null;
    return URL.createObjectURL(form.video);
  }, [form.video]);

  useEffect(() => {
    return () => {
      if (videoPreviewUrl) URL.revokeObjectURL(videoPreviewUrl);
    };
  }, [videoPreviewUrl]);

  useEffect(() => {
    fetchHealth()
      .then((h) => setFfmpegOk(h.ffmpeg_available))
      .catch(() => setFfmpegOk(false));
    fetchStages().then(setStages).catch(() => undefined);
    fetchJobs().then(setJobs).catch(() => undefined);
  }, []);

  const refreshJobs = () => {
    fetchJobs().then(setJobs).catch(() => undefined);
  };

  const handleSubmit = async () => {
    if (!form.video || !form.audio) {
      setError("Add a video and audio file before rendering.");
      return;
    }
    setError(null);
    setSubmitting(true);
    setEvents([]);
    setMediaInfo({ outputDuration: null, videoFps: null, videoSize: null });

    try {
      const { id } = await createJob({
        video: form.video,
        audio: form.audio,
        hookText: form.hookText,
        emphasisWords: form.emphasisWords,
        fillColor: form.fillColor,
        emphasisColor: form.emphasisColor,
        fontFamily: form.fontFamily,
        safePaddingPct: form.safePaddingPct,
      });

      setActiveJobId(id);
      setJobStatus("running");

      subscribeJobEvents(
        id,
        (event) => {
          setEvents((prev) => [...prev, event]);
          if (event.stage === "ingest" && event.action === "complete") {
            fetchArtifact(id, "media_info")
              .then((artifact) => {
                setMediaInfo({
                  outputDuration: artifact.output_duration_s,
                  videoFps: artifact.video.fps ?? null,
                  videoSize:
                    artifact.video.width && artifact.video.height
                      ? `${artifact.video.width}×${artifact.video.height}`
                      : null,
                });
              })
              .catch(() => undefined);
          }
        },
        () => {
          setSubmitting(false);
          setJobStatus((prev) => (prev === "running" ? "completed" : prev));
          refreshJobs();
          fetchJobs()
            .then((list) => {
              const job = list.find((j) => j.id === id);
              if (job) setJobStatus(job.status);
            })
            .catch(() => undefined);
        },
        (streamError) => {
          setSubmitting(false);
          setError(streamError.message);
          setJobStatus("failed");
          refreshJobs();
        },
      );
    } catch (err) {
      setSubmitting(false);
      setError(err instanceof Error ? err.message : "Render failed");
    }
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-monitor-border bg-monitor-surface/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-4 px-5 py-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-scope-trace">
              Local pipeline
            </p>
            <h1 className="text-lg font-semibold tracking-tight">Control Room</h1>
          </div>
          <div className="flex items-center gap-3 font-mono text-xs">
            <span
              className={
                ffmpegOk
                  ? "text-scope-trace"
                  : ffmpegOk === false
                    ? "text-hook-gold"
                    : "text-monitor-muted"
              }
            >
              {ffmpegOk === null
                ? "CHECKING FFMPEG…"
                : ffmpegOk
                  ? "FFMPEG ONLINE"
                  : "FFMPEG OFFLINE"}
            </span>
            <span className="text-monitor-muted">|</span>
            <span className="text-monitor-muted">9:16 / 60fps</span>
          </div>
        </div>
      </header>

      <main className="mx-auto grid max-w-[1400px] gap-5 px-5 py-6 lg:grid-cols-[minmax(0,1fr)_360px]">
        <section className="space-y-5">
          <div className="panel flex flex-col items-center px-6 py-8">
            <p className="mb-4 self-start font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
              Retention frame preview
            </p>
            <PhonePreview
              hookText={form.hookText}
              emphasisWords={form.emphasisWords}
              fillColor={form.fillColor}
              emphasisColor={form.emphasisColor}
              fontFamily={form.fontFamily}
              safePaddingPct={form.safePaddingPct}
              videoPreviewUrl={videoPreviewUrl}
            />
            {mediaInfo.outputDuration !== null && (
              <dl className="mt-6 grid w-full max-w-sm grid-cols-3 gap-3 font-mono text-xs">
                <div className="rounded border border-monitor-border bg-monitor-bg px-3 py-2">
                  <dt className="text-monitor-muted">OUT</dt>
                  <dd className="text-scope-trace">{mediaInfo.outputDuration.toFixed(1)}s</dd>
                </div>
                <div className="rounded border border-monitor-border bg-monitor-bg px-3 py-2">
                  <dt className="text-monitor-muted">FPS</dt>
                  <dd>{mediaInfo.videoFps?.toFixed(2) ?? "—"}</dd>
                </div>
                <div className="rounded border border-monitor-border bg-monitor-bg px-3 py-2">
                  <dt className="text-monitor-muted">SRC</dt>
                  <dd>{mediaInfo.videoSize ?? "—"}</dd>
                </div>
              </dl>
            )}
          </div>

          <JobForm
            form={form}
            onChange={setForm}
            onSubmit={handleSubmit}
            submitting={submitting}
            disabled={ffmpegOk === false}
          />

          {error && (
            <div
              role="alert"
              className="rounded-md border border-hook-gold/40 bg-hook-gold/10 px-4 py-3 text-sm text-hook-gold"
            >
              {error}
            </div>
          )}

          <OutputPanel jobId={activeJobId} status={jobStatus} />
        </section>

        <aside className="space-y-5">
          <StageTelemetry stages={stages} events={events} status={jobStatus} />

          {jobs.length > 0 && (
            <div className="panel p-4">
              <h2 className="mb-3 font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
                Recent runs
              </h2>
              <ul className="space-y-2 text-sm">
                {jobs.slice(0, 5).map((job) => (
                  <li
                    key={job.id}
                    className="flex items-center justify-between rounded border border-monitor-border bg-monitor-bg px-3 py-2"
                  >
                    <span className="truncate pr-2">{job.hook_text}</span>
                    <span className="font-mono text-xs text-monitor-muted">
                      {job.status}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </main>
    </div>
  );
}
