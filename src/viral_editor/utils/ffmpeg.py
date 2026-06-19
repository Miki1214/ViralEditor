"""FFmpeg / ffprobe subprocess wrappers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
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
