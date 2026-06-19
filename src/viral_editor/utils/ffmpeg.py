"""FFmpeg / ffprobe subprocess wrappers."""

from __future__ import annotations

import json
import shutil
import subprocess
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


def _binary_version(binary: str) -> str:
    result = subprocess.run(
        [binary, "-version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise FFmpegError(
            f"{binary} failed a version check.",
            command=[binary, "-version"],
            stderr=result.stderr,
            returncode=result.returncode,
        )
    return result.stdout.splitlines()[0] if result.stdout else binary


def ensure_ffmpeg() -> None:
    """Verify ``ffmpeg`` and ``ffprobe`` are available on PATH.

    Raises:
        EnvironmentError: If either binary is missing, with install guidance.
    """
    missing = [name for name in ("ffmpeg", "ffprobe") if shutil.which(name) is None]
    if missing:
        raise EnvironmentError(_FFMPEG_INSTALL_HINT)

    ffmpeg_line = _binary_version("ffmpeg")
    ffprobe_line = _binary_version("ffprobe")
    logger.info("FFmpeg ready: %s", ffmpeg_line)
    logger.debug("FFprobe ready: %s", ffprobe_line)


def run_ffmpeg(
    args: list[str],
    *,
    cwd: Path | None = None,
) -> subprocess.CompletedProcess[str]:
    """Run ``ffmpeg`` with logging and structured error reporting."""
    command = ["ffmpeg", *args]
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
    command = ["ffprobe", "-print_format", "json", *args]
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
