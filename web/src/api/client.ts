import type {
  HealthResponse,
  JobSummary,
  MediaInfoArtifact,
  PipelineEvent,
  StageInfo,
} from "../types";

async function parseError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (typeof body.detail === "string") return body.detail;
    return JSON.stringify(body.detail ?? body);
  } catch {
    return response.statusText;
  }
}

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch("/api/health");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchStages(): Promise<StageInfo[]> {
  const res = await fetch("/api/jobs/stages");
  if (!res.ok) throw new Error(await parseError(res));
  const data = await res.json();
  return data.stages;
}

export async function fetchJobs(): Promise<JobSummary[]> {
  const res = await fetch("/api/jobs");
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export interface CreateJobInput {
  video: File;
  audio: File;
  hookText: string;
  emphasisWords: string;
  fillColor: string;
  emphasisColor: string;
  fontFamily: string;
  safePaddingPct: number;
}

export async function createJob(input: CreateJobInput): Promise<{ id: string }> {
  const form = new FormData();
  form.append("video", input.video);
  form.append("audio", input.audio);
  form.append("hook_text", input.hookText);
  form.append("emphasis_words", input.emphasisWords);
  form.append("fill_color", input.fillColor);
  form.append("emphasis_color", input.emphasisColor);
  form.append("font_family", input.fontFamily);
  form.append("safe_padding_pct", String(input.safePaddingPct));

  const res = await fetch("/api/jobs", { method: "POST", body: form });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export function subscribeJobEvents(
  jobId: string,
  onEvent: (event: PipelineEvent) => void,
  onDone: () => void,
  onError: (error: Error) => void,
): () => void {
  const source = new EventSource(`/api/jobs/${jobId}/events`);

  source.onmessage = (message) => {
    try {
      const event = JSON.parse(message.data) as PipelineEvent;
      onEvent(event);
      if (event.stage === "pipeline" && (event.action === "complete" || event.action === "error")) {
        source.close();
        onDone();
      }
    } catch (err) {
      onError(err instanceof Error ? err : new Error("Invalid event payload"));
    }
  };

  source.onerror = () => {
    source.close();
    onError(new Error("Event stream disconnected"));
  };

  return () => source.close();
}

export async function fetchArtifact(jobId: string, name: string): Promise<MediaInfoArtifact> {
  const res = await fetch(`/api/jobs/${jobId}/artifacts/${name}`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export function outputUrl(jobId: string): string {
  return `/api/jobs/${jobId}/output`;
}
