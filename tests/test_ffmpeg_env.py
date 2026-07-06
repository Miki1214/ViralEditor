"""Tests for FFmpeg environment checks."""

from __future__ import annotations

from pathlib import Path

import pytest

from viral_editor.utils import ffmpeg as ffmpeg_module
from viral_editor.utils.ffmpeg import ensure_ffmpeg, resolve_ffmpeg_binary


def test_ensure_ffmpeg_succeeds_when_binaries_on_path() -> None:
    if not resolve_ffmpeg_binary("ffmpeg") or not resolve_ffmpeg_binary("ffprobe"):
        pytest.skip("ffmpeg/ffprobe not installed on this machine")
    ensure_ffmpeg()


def test_ensure_ffmpeg_raises_with_install_hint_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ffmpeg_module._RESOLVED_BINARIES.clear()
    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda _name: None)
    monkeypatch.setattr(ffmpeg_module, "_winget_ffmpeg_candidates", lambda _name: [])

    with pytest.raises(EnvironmentError) as exc_info:
        ensure_ffmpeg()

    message = str(exc_info.value)
    assert "winget install Gyan.FFmpeg" in message
    assert "choco install ffmpeg" in message
    assert "ffmpeg -version" in message


def test_resolve_ffmpeg_binary_falls_back_to_winget_path(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    ffmpeg_module._RESOLVED_BINARIES.clear()
    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda _name: None)

    fake_bin = tmp_path / "ffmpeg.exe"
    fake_bin.write_bytes(b"")
    fake_probe = tmp_path / "ffprobe.exe"
    fake_probe.write_bytes(b"")

    def fake_candidates(name: str) -> list[Path]:
        return [fake_bin if name == "ffmpeg" else fake_probe]

    monkeypatch.setattr(ffmpeg_module, "_winget_ffmpeg_candidates", fake_candidates)

    assert resolve_ffmpeg_binary("ffmpeg") == str(fake_bin.resolve())
    assert resolve_ffmpeg_binary("ffprobe") == str(fake_probe.resolve())


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


def test_ffmpeg_encode_progress_percent_from_progress_file() -> None:
    progress_text = "\n".join(
        [
            "frame=120",
            "out_time=00:00:02.500000",
            "progress=continue",
        ]
    )
    assert ffmpeg_module.ffmpeg_encode_progress_percent(progress_text, 10.0) == pytest.approx(25.0)


def test_ffmpeg_encode_progress_percent_caps_before_complete() -> None:
    progress_text = "out_time=00:00:12.000000\nprogress=continue\n"
    assert ffmpeg_module.ffmpeg_encode_progress_percent(progress_text, 10.0) == 99.0


def test_ffmpeg_stderr_progress_percent_parses_time() -> None:
    line = "frame=  42 fps= 30 q=28.0 size=    1024kB time=00:00:05.00 bitrate= 1234.5kbits/s speed=1.2x"
    assert ffmpeg_module.ffmpeg_stderr_progress_percent(line, 10.0) == pytest.approx(50.0)


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
