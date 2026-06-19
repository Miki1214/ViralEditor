"""Job configuration models and JSON loading."""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import Field, ValidationError, field_validator, model_validator

from viral_editor.models import BudgetPolicy, ClipInput, ClipRole, DomainModel, TeaserMask

_HEX_COLOR = re.compile(r"^#(?:[0-9A-Fa-f]{3}|[0-9A-Fa-f]{6})$")
_RGBA_COLOR = re.compile(
    r"^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(0(?:\.\d+)?|1(?:\.0+)?)\s*\)$"
)
_X264_PRESETS = frozenset(
    {"ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}
)


def _validate_color(value: str) -> str:
    if _HEX_COLOR.match(value):
        return value
    rgba = _RGBA_COLOR.match(value)
    if rgba:
        r, g, b, a = rgba.groups()
        for channel in (r, g, b):
            if int(channel) > 255:
                raise ValueError(f"RGB channel out of range in {value!r}")
        return value
    raise ValueError(
        f"Invalid color {value!r}; expected #RGB, #RRGGBB, or rgba(r,g,b,a)"
    )


def resolve_path(path: Path) -> Path:
    """Resolve relative paths against the current working directory."""
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


class ConfigError(ValueError):
    """Raised when a job config file is invalid."""


class RenderConfig(DomainModel):
    """Locked output encode settings (overridable per job)."""

    width: int = Field(default=1080, ge=1)
    height: int = Field(default=1920, ge=1)
    fps: int = Field(default=60, ge=1)
    vcodec: str = "libx264"
    acodec: str = "aac"
    crf: int = Field(default=18, ge=0, le=51)
    preset: str = "medium"
    pix_fmt: str = "yuv420p"

    @field_validator("preset")
    @classmethod
    def validate_preset(cls, value: str) -> str:
        if value not in _X264_PRESETS:
            raise ValueError(
                f"Invalid x264 preset {value!r}; expected one of: {', '.join(sorted(_X264_PRESETS))}"
            )
        return value


class StyleConfig(DomainModel):
    """Typography and overlay styling."""

    font_family: str = "Montserrat Black"
    fill_color: str = "#FFFFFF"
    emphasis_color: str = "#FFD700"
    box_color: str = "rgba(0,0,0,0.85)"
    safe_padding_pct: int = Field(default=10, ge=0, le=50)

    @field_validator("fill_color", "emphasis_color", "box_color")
    @classmethod
    def validate_colors(cls, value: str) -> str:
        return _validate_color(value)


class TitleConfig(DomainModel):
    """Hook headline text and emphasis tokens."""

    text: str = Field(min_length=1)
    emphasis_words: list[str] = Field(default_factory=list)


class SpeedRampConfig(DomainModel):
    """Speed-ramp planner parameters."""

    style: str = "drop_sync"
    s_min: float = Field(default=1.0, gt=0)
    s_max: float = Field(default=30.0, gt=0)
    alpha: float = Field(default=0.0, ge=0)
    budget_policy: BudgetPolicy = "scale"
    drop_window_ms: int = Field(default=300, ge=50, le=2000)
    min_segment_ms: int = Field(default=100, ge=10)
    speed_quantum: float = Field(default=0.5, gt=0)
    grid_step_ms: int | None = Field(default=None, ge=10)
    bass_accent: float | None = Field(default=None, ge=0, le=1)

    @model_validator(mode="after")
    def s_max_gte_s_min(self) -> SpeedRampConfig:
        if self.s_max < self.s_min:
            raise ValueError("speed_ramp.s_max must be >= speed_ramp.s_min")
        return self

    @field_validator("style")
    @classmethod
    def validate_style(cls, value: str) -> str:
        from viral_editor.video.speed_presets import PRESETS

        if value not in PRESETS:
            known = ", ".join(sorted(PRESETS))
            raise ValueError(f"speed_ramp.style must be one of: {known}")
        return value


class TeaserConfig(DomainModel):
    """Frame-0 teaser clip parameters."""

    tail_fraction: float = Field(default=0.05, gt=0, le=1)
    duration_s: float = Field(default=2.5, gt=0)
    mask: TeaserMask = "vignette"


class MusicSelectionConfig(DomainModel):
    """Target short length and selected music window for the render."""

    target_duration_s: float = Field(default=10.0, gt=0)
    use_full_track: bool = False
    selected_block_id: str | None = None
    start_s: float | None = Field(default=None, ge=0)
    end_s: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def window_end_after_start(self) -> MusicSelectionConfig:
        if self.start_s is not None and self.end_s is not None and self.end_s <= self.start_s:
            raise ValueError("music.end_s must be greater than music.start_s")
        return self


class JobConfig(DomainModel):
    """Validated job request — single source of truth for a render run."""

    video_path: Path | None = None
    audio_path: Path
    output_path: Path
    clips: list[ClipInput] = Field(default_factory=list)
    seed: int = 42
    hook: TitleConfig
    style: StyleConfig = Field(default_factory=StyleConfig)
    render: RenderConfig = Field(default_factory=RenderConfig)
    speed_ramp: SpeedRampConfig = Field(default_factory=SpeedRampConfig)
    teaser: TeaserConfig = Field(default_factory=TeaserConfig)
    music: MusicSelectionConfig = Field(default_factory=MusicSelectionConfig)

    def effective_clips(self) -> list[ClipInput]:
        """Return configured clips, or wrap a lone video_path as a single clip."""
        included = [clip for clip in self.clips if clip.included]
        if included:
            return sorted(included, key=lambda clip: clip.order)
        if self.video_path is not None:
            return [
                ClipInput(
                    id="clip_primary",
                    path=self.video_path,
                    order=0,
                    included=True,
                    role="clip",
                )
            ]
        return []

    @classmethod
    def load(cls, path: Path) -> JobConfig:
        """Load and validate a job JSON file.

        Relative paths in the file are resolved against the **current working
        directory** (not the config file's directory).
        """
        config_path = path.resolve()
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ConfigError(f"Invalid JSON in {config_path}: {exc}") from exc

        try:
            cfg = cls.model_validate(raw)
        except ValidationError as exc:
            raise ConfigError(_format_validation_error(config_path, exc)) from exc

        updates: dict = {
            "audio_path": resolve_path(cfg.audio_path),
            "output_path": resolve_path(cfg.output_path),
            "clips": [
                clip.model_copy(update={"path": resolve_path(clip.path)})
                for clip in cfg.clips
            ],
        }
        if cfg.video_path is not None:
            updates["video_path"] = resolve_path(cfg.video_path)
        return cfg.model_copy(update=updates)


def _format_validation_error(path: Path, exc: ValidationError) -> str:
    lines = [f"Invalid job config {path}:"]
    for error in exc.errors():
        location = ".".join(str(part) for part in error["loc"])
        lines.append(f"  - {location}: {error['msg']}")
    return "\n".join(lines)
