"""API request and response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from viral_editor.config import JobConfig
from viral_editor.models import SlotRole
from viral_editor.pipeline_events import PipelineEvent

JobStatus = Literal["queued", "running", "draft", "completed", "failed"]


class HealthResponse(BaseModel):
    status: str = "ok"
    ffmpeg_available: bool


class JobSummary(BaseModel):
    id: str
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


class StoryboardResponse(BaseModel):
    music_block_id: str | None = None
    music_start_s: float
    music_end_s: float
    total_duration_s: float
    loop_to_hook: bool
    slots: list[StorySlotResponse]
    preview_ready: bool = False
    teaser: TeaserSettingsResponse
    spatial_fx: SpatialFxSettingsResponse


class TeaserSettingsPatch(BaseModel):
    enabled: bool | None = None
    tail_fraction: float | None = Field(default=None, gt=0, le=1)
    duration_s: float | None = Field(default=None, gt=0)
    mask: Literal["vignette", "dir_blur"] | None = None


class SpatialFxSettingsPatch(BaseModel):
    enabled: bool | None = None
    intensity: float | None = Field(default=None, ge=0, le=1)
    max_events_per_second: float | None = Field(default=None, gt=0, le=30)


class EffectsPatchRequest(BaseModel):
    teaser: TeaserSettingsPatch | None = None
    spatial_fx: SpatialFxSettingsPatch | None = None


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
