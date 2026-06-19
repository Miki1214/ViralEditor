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
