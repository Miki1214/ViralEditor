"""Hook-oriented speed-ramp preset profiles."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from viral_editor.config import SpeedRampConfig
from viral_editor.models import BudgetPolicy

SnapMode = Literal["beat", "downbeat", "grid"]

PRESET_IDS = ("drop_sync", "slow_burn_hook", "steady_flow", "high_energy")


@dataclass(frozen=True)
class SpeedPreset:
    """Resolved tuning weights for one speed profile."""

    style: str
    label: str
    description: str
    s_min: float
    s_max: float
    alpha: float
    drop_window_ms: int
    bass_accent: float
    density_gain: float
    section_bias: float
    snap_mode: SnapMode
    opening_slow_s: float
    budget_policy: BudgetPolicy
    min_segment_ms: int
    speed_quantum: float
    grid_step_ms: int | None


PRESETS: dict[str, SpeedPreset] = {
    "drop_sync": SpeedPreset(
        style="drop_sync",
        label="Drop sync",
        description="Builds through the track and freezes on every drop at the downbeat.",
        s_min=1.0,
        s_max=30.0,
        alpha=22.0,
        drop_window_ms=350,
        bass_accent=0.15,
        density_gain=0.35,
        section_bias=0.2,
        snap_mode="downbeat",
        opening_slow_s=0.0,
        budget_policy="scale",
        min_segment_ms=100,
        speed_quantum=0.5,
        grid_step_ms=None,
    ),
    "slow_burn_hook": SpeedPreset(
        style="slow_burn_hook",
        label="Slow-burn hook",
        description="Opens gently so the hook can breathe, then accelerates toward the first drop.",
        s_min=1.0,
        s_max=24.0,
        alpha=16.0,
        drop_window_ms=400,
        bass_accent=0.1,
        density_gain=0.2,
        section_bias=0.45,
        snap_mode="downbeat",
        opening_slow_s=2.5,
        budget_policy="scale",
        min_segment_ms=120,
        speed_quantum=0.5,
        grid_step_ms=None,
    ),
    "steady_flow": SpeedPreset(
        style="steady_flow",
        label="Steady flow",
        description="Few clean speed changes with gentle ramps — safe for longer timelapses.",
        s_min=1.5,
        s_max=18.0,
        alpha=10.0,
        drop_window_ms=250,
        bass_accent=0.05,
        density_gain=0.1,
        section_bias=0.08,
        snap_mode="beat",
        opening_slow_s=0.0,
        budget_policy="scale",
        min_segment_ms=200,
        speed_quantum=1.0,
        grid_step_ms=None,
    ),
    "high_energy": SpeedPreset(
        style="high_energy",
        label="High energy",
        description="Punchy micro-slows on bass hits with frequent downbeat snaps.",
        s_min=1.0,
        s_max=28.0,
        alpha=18.0,
        drop_window_ms=280,
        bass_accent=0.55,
        density_gain=0.4,
        section_bias=0.15,
        snap_mode="downbeat",
        opening_slow_s=0.0,
        budget_policy="scale",
        min_segment_ms=80,
        speed_quantum=0.5,
        grid_step_ms=None,
    ),
}


def resolve_params(
    base: SpeedRampConfig,
    style: str,
    *,
    overrides: dict[str, float | int | str | None] | None = None,
) -> SpeedPreset:
    """Merge job config and optional PATCH overrides onto a named preset."""
    if style not in PRESETS:
        raise ValueError(f"Unknown speed ramp style {style!r}")
    preset = PRESETS[style]
    ov = overrides or {}

    def _float(key: str, default: float) -> float:
        val = ov.get(key)
        if val is None:
            val = getattr(base, key, default)
        return float(val)

    def _int(key: str, default: int) -> int:
        val = ov.get(key)
        if val is None:
            val = getattr(base, key, default)
        return int(val)

    if overrides is not None and "alpha" in overrides and overrides["alpha"] is not None:
        alpha = float(overrides["alpha"])
    elif base.alpha > 0:
        alpha = base.alpha
    else:
        alpha = preset.alpha

    return SpeedPreset(
        style=style,
        label=preset.label,
        description=preset.description,
        s_min=_float("s_min", base.s_min),
        s_max=_float("s_max", base.s_max),
        alpha=alpha,
        drop_window_ms=_int("drop_window_ms", base.drop_window_ms),
        bass_accent=float(
            ov.get(
                "bass_accent",
                base.bass_accent if base.bass_accent is not None else preset.bass_accent,
            )
        ),
        density_gain=float(ov.get("density_gain", preset.density_gain)),
        section_bias=float(ov.get("section_bias", preset.section_bias)),
        snap_mode=preset.snap_mode,
        opening_slow_s=preset.opening_slow_s,
        budget_policy=base.budget_policy,
        min_segment_ms=_int("min_segment_ms", base.min_segment_ms),
        speed_quantum=_float("speed_quantum", base.speed_quantum),
        grid_step_ms=base.grid_step_ms,
    )
