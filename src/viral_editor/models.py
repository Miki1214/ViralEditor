"""Shared domain models — the contract between pipeline stages."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T", bound=BaseModel)

TransientType = Literal["percussive", "bass", "drop"]
BudgetPolicy = Literal["scale", "loop", "trim"]
FxKind = Literal["zoom", "rotate", "translate"]
TeaserMask = Literal["vignette", "dir_blur"]
ClipRole = Literal["clip", "hook", "filler"]
SlotRole = Literal["hook", "hook_start", "hook_end", "clip", "punch"]
SlotTransition = Literal["cut", "xfade"]
SlotFitMode = Literal["contain", "cover"]


class DomainModel(BaseModel):
    """Base for all pipeline data contracts."""

    model_config = ConfigDict(extra="forbid", frozen=False)


class SpatialCrop(DomainModel):
    """Normalized crop window on the post-rotation source frame; may extend outside 0–1 for letterboxing."""

    x: float = Field(ge=-2, le=2)
    y: float = Field(ge=-2, le=2)
    w: float = Field(gt=0, le=4)
    h: float = Field(gt=0, le=4)


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


class MusicBlock(DomainModel):
    """A suggested short-form music window inside a longer track."""

    id: str
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    duration_s: float = Field(gt=0)
    score: float = Field(ge=0, le=1)
    drop_count: int = Field(ge=0)
    transient_count: int = Field(ge=0)
    label: str
    reason: str
    loop_quality: float = Field(default=0.0, ge=0, le=1)
    phrase_bars: int = Field(default=0, ge=0)
    section_label: str | None = None
    key: str | None = None
    is_repeated_section: bool = False


class MusicSection(DomainModel):
    """Structural section from beat-synchronous segmentation."""

    id: str
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)
    start_beat: int = Field(ge=0)
    end_beat: int = Field(ge=0)
    label: str
    repetition_count: int = Field(ge=1)
    energy: float = Field(ge=0, le=1)
    drop_count: int = Field(default=0, ge=0)
    is_repeated: bool = False


class MusicStructurePlan(DomainModel):
    """Structural analysis artifact."""

    sections: list[MusicSection] = Field(default_factory=list)
    key: str = "C"
    beat_engine: str = "librosa"


class MusicBlockPlan(DomainModel):
    """Ranked block suggestions for a target short duration."""

    target_duration_s: float = Field(gt=0)
    track_duration_s: float = Field(ge=0)
    selected_block_id: str | None = None
    use_full_track: bool = False
    target_match_failed: bool = False
    suggested_target_duration_s: float | None = Field(default=None, gt=0)
    blocks: list[MusicBlock] = Field(default_factory=list)


class WaveformPoint(DomainModel):
    """Single downsampled point on the onset envelope."""

    t: float = Field(ge=0)
    v: float = Field(ge=0)


class TargetLoopQuality(DomainModel):
    """Best seamless loop score for a preset target short length."""

    target_duration_s: float = Field(gt=0)
    loop_quality_pct: int = Field(ge=0, le=100)


class MusicBlockCatalog(DomainModel):
    """Precomputed block plans keyed by preset target duration (seconds as string)."""

    plans: dict[str, MusicBlockPlan] = Field(default_factory=dict)
    loop_qualities: list[TargetLoopQuality] = Field(default_factory=list)


class ScopeLaneSeries(DomainModel):
    """One downsampled lane for the Music detail rack."""

    id: str
    label: str
    points: list[WaveformPoint] = Field(default_factory=list)


class ChromaGram(DomainModel):
    """Beat-synchronous pitch-class heatmap for the Music detail rack."""

    times: list[float] = Field(default_factory=list)
    pitch_classes: list[str] = Field(default_factory=list)
    frames: list[list[float]] = Field(default_factory=list)
    tonic: str | None = None


class WaveformPayload(DomainModel):
    """Downsampled scope data for the Control Room UI."""

    duration_s: float = Field(ge=0)
    global_bpm: float = Field(gt=0)
    key: str | None = None
    beat_engine: str | None = None
    points: list[WaveformPoint] = Field(default_factory=list)
    transients: list[Transient] = Field(default_factory=list)
    beats: list[float] = Field(default_factory=list)
    downbeats: list[float] = Field(default_factory=list)
    sections: list[MusicSection] = Field(default_factory=list)
    lanes: list[ScopeLaneSeries] = Field(default_factory=list)
    chroma: ChromaGram | None = None
    blocks: list[MusicBlock] = Field(default_factory=list)
    selected_block_id: str | None = None
    target_match_failed: bool = False
    suggested_target_duration_s: float | None = Field(default=None, gt=0)
    matchable_target_durations_s: list[float] = Field(default_factory=list)
    target_loop_qualities: list[TargetLoopQuality] = Field(default_factory=list)
    best_loop_target_durations_s: list[float] = Field(default_factory=list)


class ClipInput(DomainModel):
    """User-provided source clip with optional crop and reel role."""

    id: str
    path: Path
    order: int = Field(ge=0)
    included: bool = True
    role: ClipRole = "clip"
    crop_start_s: float | None = Field(default=None, ge=0)
    crop_end_s: float | None = Field(default=None, ge=0)
    rotation_deg: int = Field(default=0, ge=0, lt=360)
    fit_mode: SlotFitMode = "contain"
    spatial_crop: SpatialCrop | None = None


class ReelEntry(DomainModel):
    """One contiguous span on the virtual reel timeline."""

    clip_id: str
    path: Path
    reel_start_s: float = Field(ge=0)
    reel_end_s: float = Field(ge=0)
    src_start_s: float = Field(ge=0)
    src_end_s: float = Field(ge=0)
    is_hook_loop: bool = False


class ClipReel(DomainModel):
    """Virtual concatenated source built from ordered clip crops."""

    entries: list[ReelEntry] = Field(default_factory=list)
    reel_duration_s: float = Field(ge=0)

    def clip_boundaries_s(self) -> list[float]:
        """Reel-time positions where the active clip changes."""
        if len(self.entries) <= 1:
            return []
        return [entry.reel_start_s for entry in self.entries[1:]]


class StorySlot(DomainModel):
    """One timed slot on the storyboard timeline awaiting a clip assignment."""

    id: str
    order: int = Field(ge=0)
    label: str
    role: SlotRole = "clip"
    out_start_s: float = Field(ge=0)
    out_end_s: float = Field(ge=0)
    target_duration_s: float = Field(gt=0)
    transition_in: SlotTransition = "cut"
    assigned_clip_id: str | None = None
    crop_start_s: float | None = Field(default=None, ge=0)
    crop_end_s: float | None = Field(default=None, ge=0)
    clip_filename: str | None = None
    rotation_deg: int = Field(default=0, ge=0, lt=360)
    fit_mode: SlotFitMode = "contain"
    spatial_crop: SpatialCrop | None = None
    rationale: str | None = None


class RetentionPlanScore(DomainModel):
    """Viral-readiness score for a music window edit plan."""

    overall: float = Field(ge=0, le=1)
    hook_strength: float = Field(ge=0, le=1)
    cadence_adherence: float = Field(ge=0, le=1)
    beat_sync: float = Field(ge=0, le=1)
    energy_coverage: float = Field(ge=0, le=1)


class Storyboard(DomainModel):
    """Ordered slot timeline derived from the selected music block."""

    music_block_id: str | None = None
    music_start_s: float = Field(ge=0)
    music_end_s: float = Field(ge=0)
    total_duration_s: float = Field(gt=0)
    loop_to_hook: bool = True
    slots: list[StorySlot] = Field(default_factory=list)
    retention_score: RetentionPlanScore | None = None


class SpeedSegment(DomainModel):
    """Piecewise-constant speed mapping between output and source time."""

    out_start_s: float = Field(ge=0)
    out_end_s: float = Field(ge=0)
    src_start_s: float = Field(ge=0)
    src_end_s: float = Field(ge=0)
    speed_factor: float = Field(gt=0)
    source_id: str | None = None


class SpeedCurvePoint(DomainModel):
    """Downsampled point on the output speed curve for UI overlay."""

    t: float = Field(ge=0)
    speed: float = Field(gt=0)
    is_slow_zone: bool = False
    is_bass_accent: bool = False


class SpeedRampPlan(DomainModel):
    """Speed-ramp planner artifact for Phase 6 render."""

    style: str = "drop_sync"
    output_duration_s: float = Field(ge=0)
    requested_output_duration_s: float | None = Field(default=None, ge=0)
    src_duration_s: float = Field(ge=0)
    budget_policy: BudgetPolicy = "scale"
    avg_speed: float = Field(default=0.0, ge=0)
    max_speed: float = Field(default=0.0, ge=0)
    min_speed: float = Field(default=0.0, ge=0)
    slow_zone_count: int = Field(default=0, ge=0)
    speed_curve: list[SpeedCurvePoint] = Field(default_factory=list)
    segments: list[SpeedSegment] = Field(default_factory=list)


class SpeedRampOption(DomainModel):
    """One hook-oriented speed profile with summary plan."""

    style: str
    label: str
    description: str
    plan: SpeedRampPlan


class SpeedRampOptionSet(DomainModel):
    """All computed speed options plus the selected style."""

    selected_style: str
    options: list[SpeedRampOption] = Field(default_factory=list)


class FxEvent(DomainModel):
    """Spatial effect impulse (zoom punch, rotation shake, or horizontal pan) at a timestamp."""

    timestamp_s: float = Field(ge=0)
    kind: FxKind
    magnitude: float = Field(gt=0)
    decay_frames: int = Field(ge=1)
    direction: int = 0  # -1 left, +1 right; 0 = derive at render for zoom/rotate
    reason: str | None = None


class TeaserSpec(DomainModel):
    """Frame-0 teaser clip extracted from the tail of the source video."""

    src_start_s: float = Field(ge=0)
    src_end_s: float = Field(ge=0)
    out_duration_s: float = Field(gt=0)
    mask: TeaserMask
    source_id: str | None = None
    source_path: Path | None = None


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


def write_artifact_list(models: list[BaseModel], name: str, temp_dir: Path) -> Path:
    """Serialize a list of domain models to ``temp_dir/<name>.json``."""
    temp_dir.mkdir(parents=True, exist_ok=True)
    path = temp_dir / f"{name}.json"
    path.write_text(
        json.dumps([model.model_dump(mode="json") for model in models], indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def read_artifact_list(model_cls: type[T], path: Path) -> list[T]:
    """Load a JSON list artifact into typed domain models."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    return [model_cls.model_validate(item) for item in payload]


def read_artifact(model_cls: type[T], path: Path) -> T:
    """Load a domain model from a JSON artifact written by ``write_artifact``."""
    return model_cls.model_validate_json(path.read_text(encoding="utf-8"))
