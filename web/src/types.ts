export type JobStatus = "queued" | "running" | "draft" | "completed" | "failed";

export type StageAction = "start" | "complete" | "skip" | "info" | "error";

export interface PipelineEvent {
  stage: string;
  action: StageAction;
  message?: string | null;
  timestamp: number;
}

export interface JobSummary {
  id: string;
  project_name: string;
  created_at: number;
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
  loop_quality: number;
  phrase_bars: number;
  section_label: string | null;
  key: string | null;
  is_repeated_section: boolean;
  expected_slot_count?: number | null;
  preset_target_duration_s?: number | null;
}

export interface MusicSection {
  id: string;
  start_s: number;
  end_s: number;
  start_beat: number;
  end_beat: number;
  label: string;
  repetition_count: number;
  energy: number;
  drop_count: number;
  is_repeated: boolean;
}

export interface MusicBlockPlan {
  target_duration_s: number;
  track_duration_s: number;
  selected_block_id: string | null;
  use_full_track: boolean;
  target_match_failed?: boolean;
  suggested_target_duration_s?: number | null;
  blocks: MusicBlock[];
}

export interface WaveformPoint {
  t: number;
  v: number;
}

export interface ScopeLaneSeries {
  id: string;
  label: string;
  points: WaveformPoint[];
}

export interface ChromaGram {
  times: number[];
  pitch_classes: string[];
  frames: number[][];
  tonic: string | null;
}

export interface TargetLoopQuality {
  target_duration_s: number;
  loop_quality_pct: number;
}

export interface WaveformPayload {
  duration_s: number;
  global_bpm: number;
  key: string | null;
  beat_engine: string | null;
  points: WaveformPoint[];
  transients: Transient[];
  beats: number[];
  downbeats: number[];
  sections: MusicSection[];
  lanes: ScopeLaneSeries[];
  chroma: ChromaGram | null;
  blocks: MusicBlock[];
  all_blocks?: MusicBlock[];
  selected_block_id: string | null;
  target_match_failed?: boolean;
  suggested_target_duration_s?: number | null;
  matchable_target_durations_s?: number[];
  target_loop_qualities?: TargetLoopQuality[];
  best_loop_target_durations_s?: number[];
}

export interface SpeedCurvePoint {
  t: number;
  speed: number;
  is_slow_zone: boolean;
  is_bass_accent: boolean;
}

export interface SpeedSegment {
  out_start_s: number;
  out_end_s: number;
  src_start_s: number;
  src_end_s: number;
  speed_factor: number;
  source_id?: string | null;
}

export type ClipRole = "clip" | "hook" | "filler";
export type SlotRole = "hook" | "hook_start" | "hook_end" | "clip" | "punch";
export type SlotTransition = "cut" | "xfade";
export type SlotFitMode = "contain" | "cover";

export interface SpatialCrop {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface StorySlot {
  id: string;
  order: number;
  label: string;
  role: SlotRole;
  out_start_s: number;
  out_end_s: number;
  target_duration_s: number;
  transition_in: SlotTransition;
  assigned_clip_id: string | null;
  crop_start_s: number | null;
  crop_end_s: number | null;
  clip_filename: string | null;
  clip_source_url: string | null;
  rotation_deg: number;
  fit_mode: SlotFitMode;
  spatial_crop: SpatialCrop | null;
  rationale?: string | null;
}

export interface RetentionPlanScore {
  overall: number;
  hook_strength: number;
  cadence_adherence: number;
  beat_sync: number;
  energy_coverage: number;
}

export interface RetentionSettings {
  interrupt_min_gap_s: number;
  interrupt_max_gap_s: number;
  hook_window_s: number;
  early_hook_fx_by_s: number;
  peak_snap_tolerance_s: number;
}

export interface StoryboardPayload {
  music_block_id: string | null;
  music_start_s: number;
  music_end_s: number;
  total_duration_s: number;
  loop_to_hook: boolean;
  preview_ready: boolean;
  render_ready: boolean;
  teaser: TeaserSettings;
  spatial_fx: SpatialFxSettings;
  retention: RetentionSettings;
  retention_score?: RetentionPlanScore | null;
  slots: StorySlot[];
}

export interface StoryboardSegmentDebugRow {
  id: string;
  role: SlotRole;
  target_duration_s: number;
  src_start_s: number;
  src_end_s: number;
  src_span_s: number;
  speed_factor: number;
  unified_label_speed: number | null;
}

export interface StoryboardSegmentsDebugPayload {
  slots: StoryboardSegmentDebugRow[];
  summary: {
    unified_crop: [number, number] | null;
    hook_budget_s: number;
    hook_speed_s: number | null;
  };
}

export type TeaserMask = "vignette" | "dir_blur";

export interface TeaserSettings {
  enabled: boolean;
  tail_fraction: number;
  duration_s: number;
  mask: TeaserMask;
  /** Valid hook-start durations on the downbeat grid; length 1 = locked. */
  payoff_downbeats_s?: number[];
}

export type PanBeatMode = "auto" | "beats" | "downbeats";

export interface SpatialFxSettings {
  enabled: boolean;
  intensity: number;
  max_events_per_second: number;
  translate_enabled: boolean;
  pan_beat_mode: PanBeatMode;
  pan_min_decay_s: number;
  pan_energy_threshold: number;
  pan_energy_floor: number;
  pan_hook_enabled: boolean;
  pan_hook_by_s: number;
}

export interface ClipInfo {
  id: string;
  filename: string;
  order: number;
  included: boolean;
  role: ClipRole;
  crop_start_s: number | null;
  crop_end_s: number | null;
  duration_s: number;
  crop_duration_s: number;
  width?: number | null;
  height?: number | null;
  fps?: number | null;
  cropStartS?: number | null;
  cropEndS?: number | null;
  durationS?: number | null;
}

export interface ClipReelResponse {
  clips: ClipInfo[];
  reel_duration_s: number;
  target_body_duration_s: number | null;
  entries: Record<string, unknown>[];
}

export interface SpeedRampPlan {
  style: string;
  output_duration_s: number;
  requested_output_duration_s: number | null;
  src_duration_s: number;
  budget_policy: string;
  avg_speed: number;
  max_speed: number;
  min_speed: number;
  slow_zone_count: number;
  speed_curve: SpeedCurvePoint[];
  segments: SpeedSegment[];
}

export interface SpeedRampOption {
  style: string;
  label: string;
  description: string;
  plan: SpeedRampPlan;
}

export interface SpeedRampOptionSet {
  selected_style: string;
  options: SpeedRampOption[];
}

export interface AudioTimeline {
  global_bpm: number;
  audio_duration_seconds: number;
  sample_rate: number;
  transients: Transient[];
}
