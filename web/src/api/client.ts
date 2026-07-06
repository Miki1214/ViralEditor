import type {
  HealthResponse,
  JobSummary,
  PipelineEvent,
  SlotFitMode,
  SpatialCrop,
  SpatialFxSettings,
  SlotTransition,
  StageInfo,
  StoryboardPayload,
  StoryboardSegmentsDebugPayload,
  TeaserSettings,
  WaveformPayload,
} from "../types";
import { DEFAULT_TARGET_DURATION_S } from "../constants/durations";

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

export interface CreateDraftJobInput {
  audio: File;
  projectName: string;
  hookText: string;
  emphasisWords: string;
  fillColor: string;
  emphasisColor: string;
  fontFamily: string;
  safePaddingPct: number;
  targetDurationS?: number;
  useFullTrack?: boolean;
}

export async function createDraftJob(input: CreateDraftJobInput): Promise<{ id: string }> {
  const form = new FormData();
  form.append("audio", input.audio);
  form.append("project_name", input.projectName);
  form.append("hook_text", input.hookText);
  form.append("emphasis_words", input.emphasisWords);
  form.append("fill_color", input.fillColor);
  form.append("emphasis_color", input.emphasisColor);
  form.append("font_family", input.fontFamily);
  form.append("safe_padding_pct", String(input.safePaddingPct));
  form.append("target_duration_s", String(input.targetDurationS ?? DEFAULT_TARGET_DURATION_S));
  form.append("use_full_track", String(input.useFullTrack ?? false));

  const res = await fetch("/api/jobs", { method: "POST", body: form });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export interface SubscribeJobEventsOptions {
  /** @deprecated Live marker after replay makes this unnecessary. */
  ignoreReplay?: boolean;
}

export function subscribeJobEvents(
  jobId: string,
  onEvent: (event: PipelineEvent) => void,
  onDone: () => void,
  onError: (error: Error) => void,
  _options: SubscribeJobEventsOptions = {},
): () => void {
  const source = new EventSource(`/api/jobs/${jobId}/events`);
  let streamLive = false;
  let finished = false;

  const finish = () => {
    if (finished) return;
    finished = true;
    source.close();
    onDone();
  };

  const isTerminal = (event: PipelineEvent) =>
    (event.stage === "render" && (event.action === "complete" || event.action === "error"))
    || (event.stage === "pipeline" && (event.action === "complete" || event.action === "error"));

  source.onmessage = (message) => {
    try {
      const event = JSON.parse(message.data) as PipelineEvent;
      if (event.stage === "sse") {
        if (event.message === "live") {
          streamLive = true;
        }
        return;
      }
      if (!streamLive) {
        return;
      }
      onEvent(event);
      if (isTerminal(event)) {
        finish();
      }
    } catch (err) {
      onError(err instanceof Error ? err : new Error("Invalid event payload"));
    }
  };

  source.onerror = () => {
    if (finished) return;
    source.close();
    onError(new Error("Event stream disconnected"));
  };

  return () => {
    finished = true;
    source.close();
  };
}

export async function fetchJob(jobId: string): Promise<JobSummary> {
  const res = await fetch(`/api/jobs/${jobId}`);
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

export function outputUrl(jobId: string, version = 0): string {
  const base = `/api/jobs/${jobId}/output`;
  if (version <= 0) {
    return base;
  }
  return `${base}?v=${version}`;
}

export async function startFinalRender(jobId: string): Promise<{ status: string }> {
  const res = await fetch(`/api/jobs/${jobId}/render`, { method: "POST" });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchStoryboard(jobId: string): Promise<StoryboardPayload> {
  const res = await fetch(`/api/jobs/${jobId}/storyboard`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function fetchStoryboardSegments(
  jobId: string,
): Promise<StoryboardSegmentsDebugPayload> {
  const res = await fetch(`/api/jobs/${jobId}/storyboard/segments`);
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function patchStoryboard(
  jobId: string,
  payload: {
    slots?: Array<{
      id: string;
      order: number;
      label?: string;
      role?: string;
      out_start_s?: number;
      out_end_s?: number;
      target_duration_s?: number;
      transition_in?: SlotTransition;
    }>;
    loop_to_hook?: boolean;
  },
): Promise<StoryboardPayload> {
  const res = await fetch(`/api/jobs/${jobId}/storyboard`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function assignSlotClip(
  jobId: string,
  slotId: string,
  file: File,
  cropStartS: number,
  cropEndS: number,
  transform?: { rotation_deg?: number; spatial_crop?: SpatialCrop | null },
): Promise<StoryboardPayload> {
  const form = new FormData();
  form.append("video", file);
  form.append("crop_start_s", String(cropStartS));
  form.append("crop_end_s", String(cropEndS));
  if (transform?.rotation_deg != null) {
    form.append("rotation_deg", String(transform.rotation_deg));
  }
  if (transform?.spatial_crop) {
    form.append("spatial_crop_json", JSON.stringify(transform.spatial_crop));
  }
  const res = await fetch(`/api/jobs/${jobId}/slots/${slotId}/clip`, {
    method: "PUT",
    body: form,
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function clearSlotClip(
  jobId: string,
  slotId: string,
): Promise<StoryboardPayload> {
  const res = await fetch(`/api/jobs/${jobId}/slots/${slotId}/clip`, {
    method: "DELETE",
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateSlotCrop(
  jobId: string,
  slotId: string,
  cropStartS: number,
  cropEndS: number,
): Promise<StoryboardPayload> {
  const res = await fetch(`/api/jobs/${jobId}/slots/${slotId}/crop`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      crop_start_s: cropStartS,
      crop_end_s: cropEndS,
    }),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function updateSlotTransform(
  jobId: string,
  slotId: string,
  payload: {
    rotation_deg?: number;
    fit_mode?: SlotFitMode;
    spatial_crop?: SpatialCrop | null;
  },
): Promise<StoryboardPayload> {
  const res = await fetch(`/api/jobs/${jobId}/slots/${slotId}/transform`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export async function patchEffects(
  jobId: string,
  payload: {
    teaser?: Partial<TeaserSettings>;
    spatial_fx?: Partial<SpatialFxSettings>;
  },
): Promise<StoryboardPayload> {
  const res = await fetch(`/api/jobs/${jobId}/effects`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(await parseError(res));
  return res.json();
}

export function compositePreviewUrl(jobId: string, force = false): string {
  const params = new URLSearchParams();
  if (force) params.set("force", "1");
  const query = params.toString();
  return `/api/jobs/${jobId}/preview${query ? `?${query}` : ""}`;
}

export async function fetchCompositePreview(
  jobId: string,
  force = false,
): Promise<
  | { ok: true; blob: Blob; url: string }
  | { ok: false; status: number; detail: string; url: string }
> {
  const url = compositePreviewUrl(jobId, force);
  const res = await fetch(url);
  if (res.ok) {
    return { ok: true, blob: await res.blob(), url };
  }
  return { ok: false, status: res.status, detail: await parseError(res), url };
}

/** @deprecated use fetchCompositePreview */
export async function probeCompositePreview(
  jobId: string,
  force = false,
): Promise<{ ok: true; url: string } | { ok: false; status: number; detail: string; url: string }> {
  const result = await fetchCompositePreview(jobId, force);
  if (result.ok) {
    return { ok: true, url: result.url };
  }
  return result;
}
