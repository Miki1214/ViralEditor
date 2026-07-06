"""FFmpeg / ffprobe subprocess wrappers."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from pathlib import Path

from viral_editor.utils.logging import get_logger

logger = get_logger(__name__)

_FFMPEG_INSTALL_HINT = (
    "FFmpeg is required but was not found on PATH.\n\n"
    "Install on Windows:\n"
    "  winget install Gyan.FFmpeg\n"
    "  choco install ffmpeg\n\n"
    "Then restart your terminal and verify:\n"
    "  ffmpeg -version\n"
    "  ffprobe -version"
)

_RESOLVED_BINARIES: dict[str, str] = {}
_STDERR_TIME_RE = re.compile(r"time=(\d+):(\d+):(\d+(?:\.\d+)?)")


class FFmpegError(RuntimeError):
    """Raised when an ffmpeg/ffprobe invocation exits non-zero."""

    def __init__(
        self,
        message: str,
        *,
        command: list[str] | None = None,
        stderr: str = "",
        returncode: int = 1,
    ) -> None:
        super().__init__(message)
        self.command = command or []
        self.stderr = stderr
        self.returncode = returncode


def _winget_ffmpeg_candidates(binary: str) -> list[Path]:
    """Common WinGet / Gyan.FFmpeg install locations on Windows."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return []

    candidates: list[Path] = []
    links = Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / f"{binary}.exe"
    if links.is_file():
        candidates.append(links)

    packages_root = Path(local_app_data) / "Microsoft" / "WinGet" / "Packages"
    if packages_root.is_dir():
        for package_dir in packages_root.glob("Gyan.FFmpeg*"):
            for exe in package_dir.glob(f"*/bin/{binary}.exe"):
                if exe.is_file():
                    candidates.append(exe)

    return candidates


def resolve_ffmpeg_binary(name: str) -> str | None:
    """Resolve ``ffmpeg`` or ``ffprobe`` on PATH or known install locations."""
    if name in _RESOLVED_BINARIES:
        return _RESOLVED_BINARIES[name]

    found = shutil.which(name)
    if found:
        _RESOLVED_BINARIES[name] = found
        return found

    if sys.platform == "win32":
        for candidate in _winget_ffmpeg_candidates(name):
            resolved = str(candidate.resolve())
            _RESOLVED_BINARIES[name] = resolved
            logger.debug("Resolved %s via WinGet path: %s", name, resolved)
            return resolved

    return None


def escape_filter_path(path: Path) -> str:
    """Escape a filesystem path for ffmpeg filter arguments."""
    resolved = path.resolve().as_posix()
    if sys.platform == "win32" and len(resolved) >= 2 and resolved[1] == ":":
        return f"{resolved[0]}\\:{resolved[2:]}"
    return resolved.replace(":", "\\:")


def resolve_drawtext_fontfile() -> str | None:
    """Return an ffmpeg-safe fontfile= path, or None if no bundled/system font exists."""
    candidates: list[Path] = []
    if sys.platform == "win32":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        candidates.extend(
            [
                windir / "Fonts" / "arial.ttf",
                windir / "Fonts" / "segoeui.ttf",
            ]
        )
    elif sys.platform == "darwin":
        candidates.extend(
            [
                Path("/System/Library/Fonts/Supplemental/Arial.ttf"),
                Path("/Library/Fonts/Arial.ttf"),
            ]
        )
    else:
        candidates.extend(
            [
                Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
                Path("/usr/share/fonts/TTF/DejaVuSans.ttf"),
            ]
        )

    for candidate in candidates:
        if candidate.is_file():
            return escape_filter_path(candidate)
    return None


def ffmpeg_available() -> bool:
    """Return True when both ffmpeg and ffprobe can be resolved."""
    return (
        resolve_ffmpeg_binary("ffmpeg") is not None
        and resolve_ffmpeg_binary("ffprobe") is not None
    )


def _binary_version(binary_path: str) -> str:
    result = subprocess.run(
        [binary_path, "-version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise FFmpegError(
            f"{binary_path} failed a version check.",
            command=[binary_path, "-version"],
            stderr=result.stderr,
            returncode=result.returncode,
        )
    return result.stdout.splitlines()[0] if result.stdout else binary_path


def ensure_ffmpeg() -> None:
    """Verify ``ffmpeg`` and ``ffprobe`` are available.

    Raises:
        EnvironmentError: If either binary is missing, with install guidance.
    """
    missing = [
        name for name in ("ffmpeg", "ffprobe") if resolve_ffmpeg_binary(name) is None
    ]
    if missing:
        raise EnvironmentError(_FFMPEG_INSTALL_HINT)

    ffmpeg_line = _binary_version(resolve_ffmpeg_binary("ffmpeg") or "ffmpeg")
    ffprobe_line = _binary_version(resolve_ffmpeg_binary("ffprobe") or "ffprobe")
    logger.info("FFmpeg ready: %s", ffmpeg_line)
    logger.debug("FFprobe ready: %s", ffprobe_line)


def _parse_hhmmss_timestamp(value: str) -> float | None:
    if value in {"", "N/A"}:
        return None
    parts = value.split(":")
    if len(parts) != 3:
        return None
    try:
        hours = int(parts[0])
        minutes = int(parts[1])
        seconds = float(parts[2])
    except ValueError:
        return None
    return hours * 3600 + minutes * 60 + seconds


def ffmpeg_encode_progress_percent(progress_text: str, duration_s: float) -> float | None:
    """Return encode completion percent from an FFmpeg ``-progress`` file snapshot."""
    if duration_s <= 0:
        return None

    out_seconds: float | None = None
    for line in progress_text.splitlines():
        if line.startswith("out_time="):
            out_seconds = _parse_hhmmss_timestamp(line.split("=", 1)[1].strip())
        elif line.startswith("out_time_us=") and out_seconds is None:
            try:
                out_seconds = int(line.split("=", 1)[1]) / 1_000_000
            except ValueError:
                continue

    if out_seconds is None:
        return None
    return min(99.0, max(0.0, 100.0 * out_seconds / duration_s))


def ffmpeg_stderr_progress_percent(stderr_line: str, duration_s: float) -> float | None:
    """Fallback percent parser for FFmpeg stderr ``time=`` stats lines."""
    if duration_s <= 0:
        return None
    match = _STDERR_TIME_RE.search(stderr_line)
    if match is None:
        return None
    hours, minutes, seconds = match.groups()
    out_seconds = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return min(99.0, max(0.0, 100.0 * out_seconds / duration_s))


def run_ffmpeg_with_progress(
    args: list[str],
    *,
    duration_s: float,
    on_progress: Callable[[float], None] | None = None,
    cwd: Path | None = None,
    poll_interval_s: float = 0.25,
) -> subprocess.CompletedProcess[str]:
    """Run ``ffmpeg`` and report encode progress against ``duration_s``."""
    ffmpeg = resolve_ffmpeg_binary("ffmpeg")
    if ffmpeg is None:
        raise EnvironmentError(_FFMPEG_INSTALL_HINT)

    with tempfile.NamedTemporaryFile(
        mode="w+",
        suffix=".ffmpeg.progress",
        delete=False,
    ) as progress_handle:
        progress_path = Path(progress_handle.name)

    command = [
        ffmpeg,
        "-hide_banner",
        "-nostats",
        "-progress",
        str(progress_path),
        *args,
    ]
    logger.debug("Running with progress: %s", " ".join(command))

    stderr_lines: list[str] = []
    last_pct = -1.0

    def emit_progress(pct: float) -> None:
        nonlocal last_pct
        if on_progress is None:
            return
        bounded = min(100.0, max(0.0, pct))
        if bounded <= last_pct + 0.9 and bounded < 100.0:
            return
        last_pct = bounded
        on_progress(bounded)

    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        cwd=str(cwd) if cwd else None,
    )

    def drain_stderr() -> None:
        if process.stderr is None:
            return
        for line in process.stderr:
            stderr_lines.append(line)
            if on_progress is not None:
                pct = ffmpeg_stderr_progress_percent(line, duration_s)
                if pct is not None:
                    emit_progress(pct)

    stderr_thread = threading.Thread(target=drain_stderr, daemon=True)
    stderr_thread.start()

    try:
        while process.poll() is None:
            if on_progress is not None and progress_path.is_file():
                try:
                    text = progress_path.read_text(encoding="utf-8", errors="replace")
                    pct = ffmpeg_encode_progress_percent(text, duration_s)
                    if pct is not None:
                        emit_progress(pct)
                except OSError:
                    pass
            time.sleep(poll_interval_s)

        process.wait()
        stderr_thread.join(timeout=5)
        stderr = "".join(stderr_lines)

        if process.returncode != 0:
            stderr_tail = "\n".join(stderr.strip().splitlines()[-20:])
            raise FFmpegError(
                f"ffmpeg exited with code {process.returncode}",
                command=command,
                stderr=stderr_tail,
                returncode=process.returncode,
            )

        emit_progress(100.0)
        return subprocess.CompletedProcess(command, process.returncode, "", stderr)
    finally:
        progress_path.unlink(missing_ok=True)


def run_ffmpeg(
    args: list[str],
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``ffmpeg`` with logging and structured error reporting."""
    ffmpeg = resolve_ffmpeg_binary("ffmpeg")
    if ffmpeg is None:
        raise EnvironmentError(_FFMPEG_INSTALL_HINT)

    command = [ffmpeg, *args]
    logger.debug("Running: %s", " ".join(command))

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
        cwd=str(cwd) if cwd else None,
    )

    if result.returncode != 0:
        stderr_tail = "\n".join(result.stderr.strip().splitlines()[-20:])
        raise FFmpegError(
            f"ffmpeg exited with code {result.returncode}",
            command=command,
            stderr=stderr_tail,
            returncode=result.returncode,
        )

    return result


def run_ffprobe_json(args: list[str]) -> dict:
    """Run ``ffprobe -print_format json`` and parse stdout."""
    ffprobe = resolve_ffmpeg_binary("ffprobe")
    if ffprobe is None:
        raise EnvironmentError(_FFMPEG_INSTALL_HINT)

    command = [ffprobe, "-print_format", "json", *args]
    logger.debug("Running: %s", " ".join(command))

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        stderr_tail = "\n".join(result.stderr.strip().splitlines()[-20:])
        raise FFmpegError(
            f"ffprobe exited with code {result.returncode}",
            command=command,
            stderr=stderr_tail,
            returncode=result.returncode,
        )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise FFmpegError(
            "ffprobe returned invalid JSON",
            command=command,
            stderr=result.stderr,
            returncode=result.returncode,
        ) from exc

    if not isinstance(payload, dict):
        raise FFmpegError(
            "ffprobe JSON root must be an object",
            command=command,
            stderr=result.stderr,
            returncode=result.returncode,
        )

    return payload
