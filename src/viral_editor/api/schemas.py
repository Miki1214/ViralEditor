"""API request and response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from viral_editor.config import CaptionConfig, JobConfig
from viral_editor.models import CaptionStyle, SlotRole
from viral_editor.pipeline_events import PipelineEvent

JobStatus = Literal["queued", "running", "draft", "completed", "failed"]


class HealthResponse(BaseModel):
    status: str = "ok"
    ffmpeg_available: bool
    whisper_available: bool = False
    whisper_runtime: str | None = None


class JobSummary(BaseModel):
    id: str
    project_name: str
    created_at: float
    status: JobStatus
    stage: str | None = None
    hook_text: str
    error: str | None = None
    output_duration_s: float | None = None
    artifacts: list[str] = Field(default_factory=list)
    has_output: bool = False


class JobDetail(JobSummary):
    config: JobConfig


class JobCreatedResponse(BaseModel):
    id: str
    status: JobStatus


class StageInfo(BaseModel):
    id: str
    label: str


class PipelineStagesResponse(BaseModel):
    stages: list[StageInfo]


class EventPayload(BaseModel):
    event: PipelineEvent


class MusicSelectionUpdate(BaseModel):
    target_duration_s: float | None = Field(default=None, gt=0)
    selected_block_id: str | None = None
    use_full_track: bool | None = None


class SpeedSelectionUpdate(BaseModel):
    style: str | None = None
    alpha: float | None = Field(default=None, ge=0)
    s_min: float | None = Field(default=None, gt=0)
    s_max: float | None = Field(default=None, gt=0)
    drop_window_ms: int | None = Field(default=None, ge=50, le=2000)
    bass_accent: float | None = Field(default=None, ge=0, le=1)


class ClipUpdate(BaseModel):
    id: str
    order: int = Field(ge=0)
    included: bool = True
    role: Literal["clip", "hook", "filler"] = "clip"
    crop_start_s: float | None = Field(default=None, ge=0)
    crop_end_s: float | None = Field(default=None, ge=0)


class ClipsPatchRequest(BaseModel):
    clips: list[ClipUpdate]


class ClipInfoResponse(BaseModel):
    id: str
    filename: str
    order: int
    included: bool
    role: Literal["clip", "hook", "filler"]
    crop_start_s: float | None
    crop_end_s: float | None
    duration_s: float
    crop_duration_s: float
    width: int | None = None
    height: int | None = None
    fps: float | None = None


class ClipReelResponse(BaseModel):
    clips: list[ClipInfoResponse]
    reel_duration_s: float
    target_body_duration_s: float | None = None
    entries: list[dict] = Field(default_factory=list)


class SpatialCropInput(BaseModel):
    x: float = Field(ge=-2, le=2)
    y: float = Field(ge=-2, le=2)
    w: float = Field(gt=0, le=4)
    h: float = Field(gt=0, le=4)


class StorySlotResponse(BaseModel):
    id: str
    order: int
    label: str
    role: SlotRole
    out_start_s: float
    out_end_s: float
    target_duration_s: float
    transition_in: Literal["cut", "xfade"]
    assigned_clip_id: str | None = None
    crop_start_s: float | None = None
    crop_end_s: float | None = None
    clip_filename: str | None = None
    clip_source_url: str | None = None
    rotation_deg: int = 0
    fit_mode: Literal["contain", "cover"] = "contain"
    spatial_crop: SpatialCropInput | None = None
    rationale: str | None = None


class RetentionPlanScoreResponse(BaseModel):
    overall: float = Field(ge=0, le=1)
    hook_strength: float = Field(ge=0, le=1)
    cadence_adherence: float = Field(ge=0, le=1)
    beat_sync: float = Field(ge=0, le=1)
    energy_coverage: float = Field(ge=0, le=1)


class RetentionSettingsResponse(BaseModel):
    interrupt_min_gap_s: float
    interrupt_max_gap_s: float
    hook_window_s: float
    early_hook_fx_by_s: float
    peak_snap_tolerance_s: float


class TeaserSettingsResponse(BaseModel):
    enabled: bool
    tail_fraction: float
    duration_s: float
    mask: Literal["vignette", "dir_blur"]
    payoff_downbeats_s: list[float] = Field(default_factory=list)


class SpatialFxSettingsResponse(BaseModel):
    enabled: bool
    intensity: float
    max_events_per_second: float
    translate_enabled: bool = True
    pan_beat_mode: Literal["auto", "beats", "downbeats"] = "auto"
    pan_min_decay_s: float = 0.2
    pan_energy_threshold: float = 0.45
    pan_energy_floor: float = 0.2
    pan_hook_enabled: bool = True
    pan_hook_by_s: float = 1.0


class StoryboardSegmentDebugRow(BaseModel):
    id: str
    role: SlotRole
    target_duration_s: float
    src_start_s: float
    src_end_s: float
    src_span_s: float
    speed_factor: float
    unified_label_speed: float | None = None


class StoryboardSegmentsSummary(BaseModel):
    unified_crop: list[float] | None = None
    hook_budget_s: float
    hook_speed_s: float | None = None


class StoryboardSegmentsDebugResponse(BaseModel):
    slots: list[StoryboardSegmentDebugRow]
    summary: StoryboardSegmentsSummary


class StoryboardResponse(BaseModel):
    music_block_id: str | None = None
    music_start_s: float
    music_end_s: float
    total_duration_s: float
    loop_to_hook: bool
    slots: list[StorySlotResponse]
    preview_ready: bool = False
    render_ready: bool = False
    teaser: TeaserSettingsResponse
    spatial_fx: SpatialFxSettingsResponse
    retention: RetentionSettingsResponse
    retention_score: RetentionPlanScoreResponse | None = None


class TeaserSettingsPatch(BaseModel):
    enabled: bool | None = None
    tail_fraction: float | None = Field(default=None, gt=0, le=1)
    duration_s: float | None = Field(default=None, gt=0)
    mask: Literal["vignette", "dir_blur"] | None = None


class SpatialFxSettingsPatch(BaseModel):
    enabled: bool | None = None
    intensity: float | None = Field(default=None, ge=0, le=1)
    max_events_per_second: float | None = Field(default=None, gt=0, le=30)
    translate_enabled: bool | None = None
    pan_beat_mode: Literal["auto", "beats", "downbeats"] | None = None
    pan_min_decay_s: float | None = Field(default=None, ge=0.1, le=0.5)
    pan_energy_threshold: float | None = Field(default=None, ge=0.15, le=0.85)
    pan_energy_floor: float | None = Field(default=None, ge=0, le=0.5)
    pan_hook_enabled: bool | None = None
    pan_hook_by_s: float | None = Field(default=None, gt=0, le=3)


class RetentionSettingsPatch(BaseModel):
    interrupt_min_gap_s: float | None = Field(default=None, gt=0, le=10)
    interrupt_max_gap_s: float | None = Field(default=None, gt=0, le=15)
    hook_window_s: float | None = Field(default=None, gt=0, le=10)
    early_hook_fx_by_s: float | None = Field(default=None, gt=0, le=10)
    peak_snap_tolerance_s: float | None = Field(default=None, gt=0, le=1)


class EffectsPatchRequest(BaseModel):
    teaser: TeaserSettingsPatch | None = None
    spatial_fx: SpatialFxSettingsPatch | None = None
    retention: RetentionSettingsPatch | None = None


class StorySlotUpdate(BaseModel):
    id: str
    order: int = Field(ge=0)
    label: str | None = None
    role: SlotRole | None = None
    out_start_s: float | None = Field(default=None, ge=0)
    out_end_s: float | None = Field(default=None, ge=0)
    target_duration_s: float | None = Field(default=None, gt=0)
    transition_in: Literal["cut", "xfade"] | None = None
    crop_start_s: float | None = Field(default=None, ge=0)
    crop_end_s: float | None = Field(default=None, gt=0)


class SlotCropPatchRequest(BaseModel):
    crop_start_s: float = Field(ge=0)
    crop_end_s: float = Field(gt=0)


class SlotTransformPatchRequest(BaseModel):
    rotation_deg: int | None = Field(default=None, ge=0, lt=360)
    fit_mode: Literal["contain", "cover"] | None = None
    spatial_crop: SpatialCropInput | None = Field(
        default=None,
        description="Normalized crop on post-rotation frame; send null to clear",
    )


class StoryboardPatchRequest(BaseModel):
    slots: list[StorySlotUpdate] | None = None
    loop_to_hook: bool | None = None


class CaptionStylePatch(BaseModel):
    font_family: str | None = None
    fill_color: str | None = None
    emphasis_color: str | None = None
    outline_color: str | None = None
    outline_enabled: bool | None = None
    box_enabled: bool | None = None
    box_color: str | None = None
    position: Literal["top", "center", "bottom"] | None = None
    size_scale: float | None = Field(default=None, gt=0, le=3.0)
    safe_padding_pct: int | None = Field(default=None, ge=0, le=50)
    karaoke_enabled: bool | None = None


class CaptionWordResponse(BaseModel):
    text: str
    start_s: float
    end_s: float
    emphasis: bool = False


class CaptionChunkResponse(BaseModel):
    words: list[CaptionWordResponse]
    start_s: float
    end_s: float


class CaptionStyleResponse(BaseModel):
    font_family: str
    fill_color: str
    emphasis_color: str
    outline_color: str
    outline_enabled: bool
    box_enabled: bool
    box_color: str
    position: Literal["top", "center", "bottom"]
    size_scale: float
    safe_padding_pct: int
    karaoke_enabled: bool


class WpsPresetResponse(BaseModel):
    words_per_second: float
    label: str


class SlotCaptionBudgetResponse(BaseModel):
    slot_id: str
    label: str
    duration_s: float
    suggested_words: int
    actual_words: int
    has_asr_timing: bool = False
    chunks: list[CaptionChunkResponse] = Field(default_factory=list)


class CaptionResponse(BaseModel):
    script_text: str
    words_per_second: float
    hook_text: str
    emphasis_words: list[str]
    hook_style: CaptionStyleResponse
    caption_style: CaptionStyleResponse
    slot_overrides: dict[str, str] = Field(default_factory=dict)
    slot_budgets: list[SlotCaptionBudgetResponse] = Field(default_factory=list)
    wps_presets: list[WpsPresetResponse] = Field(default_factory=list)
    transcribe_available: bool = False
    audio_sync_available: bool = False


class CaptionPatchRequest(BaseModel):
    script_text: str | None = None
    words_per_second: float | None = Field(default=None, gt=0, le=15)
    hook_text: str | None = None
    emphasis_words: list[str] | None = None
    hook_style: CaptionStylePatch | None = None
    caption_style: CaptionStylePatch | None = None
    slot_overrides: dict[str, str] | None = None
    word_timing_overrides: dict[str, list[dict[str, float | str]]] | None = None
    karaoke_enabled: bool | None = None
    cleanup: bool = False
    auto_allocate: bool = False
    audio_sync: bool = False


class TranscribeCaptionResponse(BaseModel):
    script_text: str
    words: list[CaptionWordResponse]
    slot_overrides: dict[str, str] = Field(default_factory=dict)
    word_timing_overrides: dict[str, list[dict[str, float | str]]] = Field(
        default_factory=dict
    )
    source: str = "audio_track"
    language: str | None = None
    translate: bool = False
    skipped_clip_ids: list[str] = Field(default_factory=list)
    transcribe_available: bool = True
