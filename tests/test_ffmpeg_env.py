"""Tests for FFmpeg environment checks."""

from __future__ import annotations

import shutil

import pytest

from viral_editor.utils import ffmpeg as ffmpeg_module
from viral_editor.utils.ffmpeg import ensure_ffmpeg


def test_ensure_ffmpeg_succeeds_when_binaries_on_path() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        pytest.skip("ffmpeg/ffprobe not installed on this machine")
    ensure_ffmpeg()


def test_ensure_ffmpeg_raises_with_install_hint_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda _name: None)

    with pytest.raises(EnvironmentError) as exc_info:
        ensure_ffmpeg()

    message = str(exc_info.value)
    assert "winget install Gyan.FFmpeg" in message
    assert "choco install ffmpeg" in message
    assert "ffmpeg -version" in message


def test_run_ffprobe_json_parses_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = {"format": {"duration": "1.0"}, "streams": []}

    class FakeResult:
        returncode = 0
        stdout = __import__("json").dumps(payload)
        stderr = ""

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", lambda *a, **k: FakeResult())
    assert ffmpeg_module.run_ffprobe_json(["-show_format"]) == payload


def test_run_ffmpeg_raises_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeResult:
        returncode = 1
        stdout = ""
        stderr = "error: invalid option\n"

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", lambda *a, **k: FakeResult())

    from viral_editor.utils.ffmpeg import FFmpegError, run_ffmpeg

    with pytest.raises(FFmpegError) as exc_info:
        run_ffmpeg(["-invalid-flag"])

    assert exc_info.value.returncode == 1
    assert "invalid option" in exc_info.value.stderr
