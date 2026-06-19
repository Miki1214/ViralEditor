# Phase 0 - Project Scaffolding & Environment

**Goal:** A clean, runnable Python project skeleton with dependency management, FFmpeg verification, structured logging, and shared domain models in place, so every later phase plugs into a stable contract.

**Status:** Core - foundational, blocks all other phases.

---

## Objective

Stand up the repository structure, tooling, and the cross-cutting concerns (logging, FFmpeg wrapper, domain models) that every subsequent phase depends on. No video logic yet, but the pipeline "rails" are laid.

## Deliverables

- Project layout under `src/viral_editor/`.
- `requirements.txt`, `.gitignore`, `README.md`.
- `utils/ffmpeg.py` with FFmpeg/FFprobe availability check + thin invocation wrapper.
- `utils/logging.py` with a configured structured logger.
- `models.py` with all shared domain models (stubs/fields, no behavior yet).
- `cli.py` entrypoint that parses args and prints a "not yet implemented" pipeline (wired in Phase 7).

## Proposed layout

```
ViralAutomation/
  README.md
  requirements.txt
  .gitignore
  config/
    job.example.json          # filled in Phase 1
  assets/                      # user-provided sample video + music (gitignored content)
  output/                      # gitignored
  temp/                        # gitignored per-stage artifacts
  src/viral_editor/
    __init__.py
    cli.py
    config.py                  # Phase 1
    models.py
    pipeline.py                # Phase 7 (stub now)
    utils/
      __init__.py
      ffmpeg.py
      logging.py
    ingest/__init__.py
    audio/__init__.py
    video/__init__.py
    overlay/__init__.py
    render/__init__.py
  tests/
    __init__.py
    conftest.py
```

## Files & responsibilities

### `requirements.txt`
Pin major libraries (let the installer resolve patch versions):

```
librosa>=0.10
numpy>=1.26
scipy>=1.11
soundfile>=0.12
pydantic>=2.5
typer>=0.12          # CLI (or stdlib argparse if we want zero deps)
rich>=13.7           # pretty logging/console
pytest>=8.0          # dev/test
```

> FFmpeg itself is a **system binary**, not a pip package. We deliberately avoid `ffmpeg-python`/`moviepy` for the core graph to keep full control of `filter_complex`; the wrapper calls the binary via `subprocess`.

### `.gitignore`
Ignore `output/`, `temp/`, `.venv/`, `__pycache__/`, `*.pyc`, and large media under `assets/` (keep a small README or `.gitkeep`).

### `utils/ffmpeg.py`
- `ensure_ffmpeg() -> None`: checks `ffmpeg -version` and `ffprobe -version` on PATH; raises a clear `EnvironmentError` with Windows install guidance (`winget install Gyan.FFmpeg` or `choco install ffmpeg`) if missing.
- `run_ffmpeg(args: list[str], *, cwd=None) -> CompletedProcess`: wraps `subprocess.run`, captures stderr, logs the full command, raises a typed `FFmpegError` (with stderr tail) on non-zero exit.
- `run_ffprobe_json(args: list[str]) -> dict`: runs `ffprobe -print_format json` and parses output.
- Centralizing here means later phases never build raw `subprocess` calls.

### `utils/logging.py`
- `get_logger(name)` returning a `rich`-backed logger with consistent formatting and a `--verbose` switch hook.
- Stage helpers (e.g., `log_stage("audio")`) for uniform stage boundaries.

### `models.py`
Declare all shared models (see README "Shared domain models"). Use `pydantic.BaseModel` with `model_config = ConfigDict(extra="forbid")` and a helper to dump to `temp/<stage>.json`. Keep them behavior-free data contracts.

### `cli.py`
- Define the `run` command signature: `viral-editor run <config.json> [--verbose] [--keep-temp]`.
- For now it calls `ensure_ffmpeg()` and logs "pipeline stub"; real wiring lands in [Phase 7](phase-7-cli-e2e.md).

### `README.md`
Setup on Windows:
1. `python -m venv .venv` then `.venv\Scripts\Activate.ps1`
2. `pip install -r requirements.txt`
3. Install FFmpeg (`winget install Gyan.FFmpeg`) and confirm `ffmpeg -version`
4. `python -m viral_editor run config/job.example.json`

## Dependencies

None (this phase unblocks all others).

## Testing

- `tests/test_ffmpeg_env.py`: `ensure_ffmpeg()` passes when present; monkeypatch PATH to assert the helpful error otherwise.
- `tests/test_models.py`: round-trip serialize/deserialize each domain model.
- Confirm `python -m viral_editor run ...` imports cleanly and reports FFmpeg status.

## Acceptance criteria

- Fresh clone -> venv -> install -> `python -m viral_editor run` runs without import errors and reports FFmpeg availability.
- `pytest` green.
- All shared models importable from `viral_editor.models`.

## Risks & mitigations

- **FFmpeg not on PATH (Windows):** `ensure_ffmpeg()` gives copy-paste install commands.
- **Dependency drift (librosa/numba build issues on Windows):** pin minimums, document Python 3.11 as the supported interpreter (best librosa/numba wheel support).
