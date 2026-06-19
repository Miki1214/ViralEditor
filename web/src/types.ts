export type JobStatus = "queued" | "running" | "completed" | "failed";

export type StageAction = "start" | "complete" | "skip" | "info" | "error";

export interface PipelineEvent {
  stage: string;
  action: StageAction;
  message?: string | null;
  timestamp: number;
}

export interface JobSummary {
  id: string;
  status: JobStatus;
  stage: string | null;
  hook_text: string;
  error: string | null;
  output_duration_s: number | null;
  artifacts: string[];
  has_output: boolean;
}

export interface StageInfo {
  id: string;
  label: string;
}

export interface HealthResponse {
  status: string;
  ffmpeg_available: boolean;
}

export interface MediaInfoArtifact {
  video: {
    duration_s: number;
    width?: number | null;
    height?: number | null;
    fps?: number | null;
  };
  audio: {
    duration_s: number;
    sample_rate?: number | null;
  };
  output_duration_s: number;
}

export interface Transient {
  timestamp_ms: number;
  amplitude_normalized: number;
  type: "drop" | "bass" | "percussive";
}

export interface MusicBlock {
  id: string;
  start_s: number;
  end_s: number;
  duration_s: number;
  score: number;
  drop_count: number;
  transient_count: number;
  label: string;
  reason: string;
}

export interface MusicBlockPlan {
  target_duration_s: number;
  track_duration_s: number;
  selected_block_id: string | null;
  use_full_track: boolean;
  blocks: MusicBlock[];
}

export interface WaveformPoint {
  t: number;
  v: number;
}

export interface WaveformPayload {
  duration_s: number;
  global_bpm: number;
  points: WaveformPoint[];
  transients: Transient[];
  blocks: MusicBlock[];
  selected_block_id: string | null;
}

export interface AudioTimeline {
  global_bpm: number;
  audio_duration_seconds: number;
  sample_rate: number;
  transients: Transient[];
}
