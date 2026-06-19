"""Shared domain models — the contract between pipeline stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)

TransientType = Literal["percussive", "bass", "drop"]
FxKind = Literal["zoom", "rotate"]
TeaserMask = Literal["vignette", "dir_blur"]


class DomainModel(BaseModel):
    """Base for all pipeline data contracts."""

    model_config = ConfigDict(extra="forbid", frozen=False)


class MediaInfo(DomainModel):
    """Probed metadata for a video or audio stream."""

    path: Path
    duration_s: float = Field(ge=0)
    has_video: bool = False
    has_audio: bool = False
    width: int | None = Field(default=None, ge=1)
    height: int | None = Field(default=None, ge=1)
    fps: float | None = Field(default=None, gt=0)
    r_frame_rate_raw: str | None = None
    codec_name: str | None = None
    sample_rate: int | None = Field(default=None, ge=1)
    channels: int | None = Field(default=None, ge=1)


class Transient(DomainModel):
    """A detected audio hit aligned to the music timeline."""

    timestamp_ms: int = Field(ge=0)
    amplitude_normalized: float = Field(ge=0, le=1)
    type: TransientType


class AudioTimeline(DomainModel):
    """Beat/transient analysis output from the audio DSP stage."""

    global_bpm: float = Field(gt=0)
    audio_duration_seconds: float = Field(ge=0)
    sample_rate: int = Field(ge=1)
    transients: list[Transient] = Field(default_factory=list)


class SpeedSegment(DomainModel):
    """Piecewise-constant speed mapping between output and source time."""

    out_start_s: float = Field(ge=0)
    out_end_s: float = Field(ge=0)
    src_start_s: float = Field(ge=0)
    src_end_s: float = Field(ge=0)
    speed_factor: float = Field(gt=0)


class FxEvent(DomainModel):
    """Spatial effect impulse (zoom punch or rotation shake) at a timestamp."""

    timestamp_s: float = Field(ge=0)
    kind: FxKind
    magnitude: float = Field(gt=0)
    decay_frames: int = Field(ge=1)


class TeaserSpec(DomainModel):
    """Frame-0 teaser clip extracted from the tail of the source video."""

    src_start_s: float = Field(ge=0)
    src_end_s: float = Field(ge=0)
    out_duration_s: float = Field(gt=0)
    mask: TeaserMask


class EmphasisSpec(DomainModel):
    """Duotone emphasis tokens within hook text."""

    words: list[str] = Field(default_factory=list)
    color: str


class BoxSpec(DomainModel):
    """Background pill / shadow box behind title text."""

    color: str
    padding_px: int = Field(ge=0)
    radius_px: int = Field(ge=0)


class SafeRect(DomainModel):
    """Platform-safe viewport inset (clears native UI chrome)."""

    x: int = Field(ge=0)
    y: int = Field(ge=0)
    w: int = Field(ge=1)
    h: int = Field(ge=1)


class TimeWindow(DomainModel):
    """Inclusive start, exclusive end overlay window in seconds."""

    start: float = Field(ge=0)
    end: float = Field(ge=0)


class TitleSpec(DomainModel):
    """Hook text overlay layout for the teaser window."""

    lines: list[str] = Field(min_length=1)
    font: str
    size_px: int = Field(ge=1)
    fill: str
    emphasis: EmphasisSpec
    box: BoxSpec
    anchor: str = "center"
    safe_rect: SafeRect
    window_s: TimeWindow


class RenderPlan(DomainModel):
    """Aggregate plan consumed by the FFmpeg builder (Phase 6)."""

    output_duration_s: float = Field(ge=0)
    speed_segments: list[SpeedSegment] = Field(default_factory=list)
    teaser: TeaserSpec | None = None
    fx_events: list[FxEvent] = Field(default_factory=list)
    title: TitleSpec | None = None


def write_artifact(model: BaseModel, name: str, temp_dir: Path) -> Path:
    """Serialize a domain model to ``temp_dir/<name>.json`` for inspection."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    path = temp_dir / f"{name}.json"
    path.write_text(
        json.dumps(model.model_dump(mode="json"), indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def read_artifact(model_cls: type[T], path: Path) -> T:
    """Load a domain model from a JSON artifact written by ``write_artifact``."""
    return model_cls.model_validate_json(path.read_text(encoding="utf-8"))
