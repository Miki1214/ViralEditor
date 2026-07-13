"""Run Control Room API + Vite dev server together."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
WEB_DIR = REPO_ROOT / "web"


class DevStartupError(RuntimeError):
    """Raised when dev prerequisites are missing."""


def _require_ui_deps() -> None:
    try:
        import uvicorn  # noqa: F401
    except ImportError as exc:
        raise DevStartupError(
            'uvicorn is required for dev. Install with: pip install -e ".[ui]"'
        ) from exc

    if shutil.which("npm") is None:
        raise DevStartupError("npm not found on PATH. Install Node.js to run the UI dev server.")

    if not (WEB_DIR / "package.json").is_file():
        raise DevStartupError(f"Missing {WEB_DIR / 'package.json'}")

    if not (WEB_DIR / "node_modules").is_dir():
        raise DevStartupError("Web dependencies not installed. Run: cd web && npm install")


def build_api_command(*, host: str, port: int, reload: bool) -> list[str]:
    cmd = [
        sys.executable,
        "-m",
        "uvicorn",
        "viral_editor.api.main:create_app",
        "--factory",
        "--host",
        host,
        "--port",
        str(port),
    ]
    if reload:
        cmd.append("--reload")
    return cmd


def build_ui_command() -> list[str]:
    npm = shutil.which("npm")
    if npm is None:
        raise DevStartupError("npm not found on PATH. Install Node.js to run the UI dev server.")
    return [npm, "run", "dev"]


def _terminate(proc: subprocess.Popen[bytes], timeout_s: float = 5.0) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=timeout_s)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def run_dev(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    reload: bool = True,
) -> int:
    """Start API (uvicorn) and Vite; block until one exits or Ctrl+C."""
    _require_ui_deps()

    api_proc = subprocess.Popen(build_api_command(host=host, port=port, reload=reload))  # noqa: S603
    ui_proc = subprocess.Popen(build_ui_command(), cwd=WEB_DIR)  # noqa: S603
    procs = [api_proc, ui_proc]

    def shutdown() -> None:
        for proc in procs:
            _terminate(proc)

    print(f"Control Room UI:  http://localhost:5173")
    print(f"Control Room API: http://{host}:{port}/api/health")
    print("Press Ctrl+C to stop both servers.")

    exit_code = 0
    try:
        while True:
            for proc in procs:
                code = proc.poll()
                if code is not None:
                    exit_code = code
                    shutdown()
                    return exit_code
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    finally:
        shutdown()

    return exit_code
