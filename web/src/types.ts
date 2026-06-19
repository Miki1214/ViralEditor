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
