import type {
  HealthResponse,
  JobSummary,
  PipelineEvent,
  SlotFitMode,
  SpatialCrop,
  SlotTransition,
  StageInfo,
  StoryboardPayload,
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

export async function fetchStoryboard(jobId: string): Promise<StoryboardPayload> {
  const res = await fetch(`/api/jobs/${jobId}/storyboard`);
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

export function compositePreviewUrl(jobId: string, force = false): string {
  const params = new URLSearchParams();
  if (force) params.set("force", "1");
  const query = params.toString();
  return `/api/jobs/${jobId}/preview${query ? `?${query}` : ""}`;
}
