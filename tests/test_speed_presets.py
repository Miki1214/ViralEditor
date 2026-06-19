"""Tests for speed-ramp preset profiles."""

from __future__ import annotations

import pytest

from viral_editor.config import SpeedRampConfig
from viral_editor.video.speed_presets import PRESETS, PRESET_IDS, resolve_params


def test_all_preset_ids_resolve() -> None:
    base = SpeedRampConfig()
    for style in PRESET_IDS:
        params = resolve_params(base, style)
        assert params.style == style
        assert params.label
        assert params.s_max >= params.s_min


def test_unknown_style_raises() -> None:
    with pytest.raises(ValueError, match="Unknown speed ramp"):
        resolve_params(SpeedRampConfig(), "not_a_preset")


def test_overrides_merge_on_top_of_preset() -> None:
    params = resolve_params(
        SpeedRampConfig(style="steady_flow"),
        "steady_flow",
        overrides={"alpha": 0.0, "bass_accent": 0.9},
    )
    assert params.alpha == 0.0
    assert params.bass_accent == 0.9


def test_config_alpha_overrides_preset_default() -> None:
    params = resolve_params(SpeedRampConfig(alpha=4.5), "drop_sync")
    assert params.alpha == 4.5


def test_preset_keys_match_registry() -> None:
    assert set(PRESETS.keys()) == set(PRESET_IDS)
