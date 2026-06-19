"""Tests for job configuration loading and validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from viral_editor.config import ConfigError, JobConfig, resolve_path


def _write_job(tmp_path: Path, payload: dict) -> Path:
    path = tmp_path / "job.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _minimal_job_payload(**overrides: object) -> dict:
    payload = {
        "video_path": "input/video.mp4",
        "audio_path": "input/track.mp3",
        "output_path": "output/result.mp4",
        "hook": {"text": "Hello world"},
    }
    payload.update(overrides)
    return payload


def test_minimal_job_loads_with_defaults(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    job_path = _write_job(tmp_path, _minimal_job_payload())

    cfg = JobConfig.load(job_path)

    assert cfg.video_path == (tmp_path / "input/video.mp4").resolve()
    assert cfg.render.width == 1080
    assert cfg.render.height == 1920
    assert cfg.render.fps == 60
    assert cfg.style.fill_color == "#FFFFFF"
    assert cfg.speed_ramp.s_max == 30.0
    assert cfg.teaser.mask == "vignette"
    assert cfg.hook.text == "Hello world"
    assert cfg.hook.emphasis_words == []


def test_full_job_loads_all_sections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    job_path = _write_job(
        tmp_path,
        _minimal_job_payload(
            seed=7,
            hook={"text": "Hook", "emphasis_words": ["Hook"]},
            style={"fill_color": "#000000", "emphasis_color": "#FF0000", "box_color": "rgba(0,0,0,0.5)"},
            render={"fps": 30, "crf": 20},
            speed_ramp={"s_min": 0.5, "s_max": 20.0, "alpha": 1.5},
            teaser={"tail_fraction": 0.1, "duration_s": 3.0, "mask": "dir_blur"},
        ),
    )

    cfg = JobConfig.load(job_path)

    assert cfg.seed == 7
    assert cfg.render.fps == 30
    assert cfg.render.crf == 20
    assert cfg.speed_ramp.alpha == 1.5
    assert cfg.teaser.mask == "dir_blur"


def test_unknown_key_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    job_path = _write_job(tmp_path, _minimal_job_payload(unknown_field="nope"))

    with pytest.raises(ConfigError) as exc_info:
        JobConfig.load(job_path)

    assert "unknown_field" in str(exc_info.value)


def test_bad_color_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    job_path = _write_job(
        tmp_path,
        _minimal_job_payload(style={"fill_color": "not-a-color"}),
    )

    with pytest.raises(ConfigError) as exc_info:
        JobConfig.load(job_path)

    assert "fill_color" in str(exc_info.value)


def test_bad_teaser_mask_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    job_path = _write_job(
        tmp_path,
        _minimal_job_payload(teaser={"mask": "blur"}),
    )

    with pytest.raises(ConfigError) as exc_info:
        JobConfig.load(job_path)

    assert "teaser" in str(exc_info.value)


def test_speed_ramp_s_max_below_s_min_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    job_path = _write_job(
        tmp_path,
        _minimal_job_payload(speed_ramp={"s_min": 10.0, "s_max": 5.0}),
    )

    with pytest.raises(ConfigError) as exc_info:
        JobConfig.load(job_path)

    assert "s_max" in str(exc_info.value)


def test_resolve_path_relative_to_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    assert resolve_path(Path("assets/video.mp4")) == (tmp_path / "assets/video.mp4").resolve()


def test_resolve_path_absolute_unchanged(tmp_path: Path) -> None:
    absolute = (tmp_path / "abs.mp4").resolve()
    assert resolve_path(absolute) == absolute


def test_absolute_paths_in_job(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    video = tmp_path / "video.mp4"
    audio = tmp_path / "audio.mp3"
    output = tmp_path / "out" / "result.mp4"
    job_path = _write_job(
        tmp_path,
        {
            "video_path": str(video),
            "audio_path": str(audio),
            "output_path": str(output),
            "hook": {"text": "Test"},
        },
    )

    cfg = JobConfig.load(job_path)

    assert cfg.video_path == video.resolve()
    assert cfg.audio_path == audio.resolve()
    assert cfg.output_path == output.resolve()
