"""API request and response schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from viral_editor.config import JobConfig
from viral_editor.pipeline_events import PipelineEvent

JobStatus = Literal["queued", "running", "completed", "failed"]


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
