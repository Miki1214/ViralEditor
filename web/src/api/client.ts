import type {
  HealthResponse,
  JobSummary,
  MediaInfoArtifact,
  MusicBlock,
  PipelineEvent,
  SpeedRampOptionSet,
  StageInfo,
  WaveformPayload,
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
  targetDurationS?: number;
  useFullTrack?: boolean;
  selectedBlockId?: string | null;
  musicStartS?: number | null;
  musicEndS?: number | null;
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
  form.append("target_duration_s", String(input.targetDurationS ?? 30));
  form.append("use_full_track", String(input.useFullTrack ?? false));
  if (input.selectedBlockId) {
    form.append("selected_block_id", input.selectedBlockId);
  }
  if (input.musicStartS != null) {
    form.append("music_start_s", String(input.musicStartS));
  }
  if (input.musicEndS != null) {
    form.append("music_end_s", String(input.musicEndS));
  }

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

export async function fetchWaveform(jobId: string): Promise<WaveformPayload> {
  const res = await fetch(`/api/jobs/${jobId}/audio/waveform`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateMusicSelection(
  jobId: string,
  payload: {
    target_duration_s?: number;
    selected_block_id?: string;
    use_full_track?: boolean;
  },
): Promise<void> {
  const res = await fetch(`/api/jobs/${jobId}/music-selection`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
}

export function previewAudioUrl(jobId: string, startS: number, endS: number): string {
  const params = new URLSearchParams({
    start_s: String(startS),
    end_s: String(endS),
  });
  return `/api/jobs/${jobId}/audio/preview?${params.toString()}`;
}

export function loopSeamPreviewUrl(jobId: string, startS: number, endS: number): string {
  const params = new URLSearchParams({
    start_s: String(startS),
    end_s: String(endS),
    loop_only: "true",
  });
  return `/api/jobs/${jobId}/audio/preview?${params.toString()}`;
}

export function outputUrl(jobId: string): string {
  return `/api/jobs/${jobId}/output`;
}

export async function fetchSpeedRamp(jobId: string): Promise<SpeedRampOptionSet> {
  const res = await fetch(`/api/jobs/${jobId}/speed-ramp`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateSpeedSelection(
  jobId: string,
  payload: {
    style?: string;
    alpha?: number;
    s_min?: number;
    s_max?: number;
    drop_window_ms?: number;
    bass_accent?: number;
  },
): Promise<SpeedRampOptionSet> {
  const res = await fetch(`/api/jobs/${jobId}/speed-selection`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export function speedProxyPreviewUrl(jobId: string, style: string, force = false): string {
  const params = new URLSearchParams({ style });
  if (force) params.set("force", "1");
  return `/api/jobs/${jobId}/speed-ramp/preview?${params.toString()}`;
}
