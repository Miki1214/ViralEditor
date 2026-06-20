# Viral Editor

Local-first Python CLI that turns a timelapse video plus a music track into a high-retention vertical short (`1080x1920`, H.264 + AAC, 60 fps). FFmpeg handles rendering; Python orchestrates a modular, testable pipeline.

## Requirements

- **Python 3.11+** (best librosa/numba wheel support on Windows)
- **FFmpeg 6.x** on `PATH` (`ffmpeg` and `ffprobe`)

## Setup (Windows)

Use a **project virtualenv** — do not install into system Python (`C:\Python312`), or scripts may fail to land on PATH.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[ui,dev]"
```

After activation, run commands with either form:

```powershell
python -m viral_editor serve    # always works
viral-editor serve              # same, if Scripts is on PATH
```

Install FFmpeg if missing:

```powershell
winget install Gyan.FFmpeg
# or: choco install ffmpeg
ffmpeg -version
ffprobe -version
```

Place sample assets under `assets/` (see `assets/README.md`). Job configs live in `config/`.

## Control Room UI (Option A)

Local web dashboard for configuring jobs, watching pipeline telemetry, and previewing output.

### Development (two terminals)

```powershell
# Terminal 1 — API (with venv activated)
python -m viral_editor serve

# Terminal 2 — UI with hot reload
cd web
npm install
npm run dev
```

Open http://localhost:5173 (Vite proxies `/api` to the API on port 8765).

### Production-style (single server)

```powershell
cd web && npm install && npm run build
cd ..
python -m viral_editor serve
```

Open http://127.0.0.1:8765 — serves the built UI from `web/dist/`.

### Docker (recommended for beat-this neural tracking)

The container includes FFmpeg, PyTorch (CPU), and the `beat-this` downbeat tracker. Model weights cache in a named volume after first run.

```powershell
docker compose up --build
```

Open http://127.0.0.1:8765. Bind-mounts:

- `./input` — drop source files
- `./output` — rendered results
- `./temp` — job workspaces (optional inspection)

**Demucs vocal separation:** loop planning uses the `htdemucs` model (via `demucs` + `torch`, installed by default). Weights download on first analysis and cache under `TORCH_HOME` (default `~/.cache/torch`). Set `DEMUCS_MODEL_CACHE` to pin the cache directory (e.g. a Docker volume).

**GPU (recommended for Demucs):** the default `pip install` pulls a **CPU-only** PyTorch wheel (`+cpu`). `pip install --upgrade … --index-url cu124` alone will **not** replace it — pip sees `torch 2.12.1` as already satisfied. Uninstall first, then install CUDA wheels:

```powershell
.venv\Scripts\Activate.ps1
pip uninstall torch torchaudio -y
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'no gpu')"
```

You should see a `+cu124` version and `True`. Demucs then auto-selects your NVIDIA GPU (`DEMUCS_DEVICE=auto`, the default). Progress will show `GPU · <your card name>`. Force CPU with `DEMUCS_DEVICE=cpu`.

CPU tuning: default **8 parallel chunk jobs** (`DEMUCS_NUM_WORKERS`), `shifts=0`, `overlap=0.15`. Vocal stems cache per job as `temp/vocal_stem_demucs.npz`.

For neural beat tracking locally (optional extra):

```powershell
pip install -e ".[ui,dev,audio-nn]" --extra-index-url https://download.pytorch.org/whl/cpu
```

## Usage (CLI)

```powershell
python -m viral_editor run config/job.example.json
python -m viral_editor run config/job.example.json --verbose
```

The pipeline is a stub in Phase 0; full end-to-end wiring lands in Phase 7.

**Phase 1:** loads and validates the job JSON, probes video/audio with ffprobe, writes `temp/media_info.json`, and derives `output_duration_s` from the music track.

**Phase 2 (current):** runs beat/downbeat tracking (beat-this when installed, else librosa), beat-synchronous MIR features, structural segmentation, and loop-aware block suggestions. Writes `temp/audio_timeline.json`, `temp/onset_envelope.npy`, `temp/features.npz`, `temp/music_structure.json`, and `temp/music_blocks.json`.

## Project layout

```
src/viral_editor/     # application package
  cli.py              # Typer entrypoint
  models.py           # shared domain models (stage contracts)
  pipeline.py         # orchestrator (stub)
  utils/ffmpeg.py     # FFmpeg/ffprobe wrapper
  utils/logging.py    # structured logging
config/               # job JSON files
assets/               # input media (gitignored)
output/               # rendered MP4s (gitignored)
temp/                 # per-stage JSON artifacts (gitignored)
tests/
```

## Shared domain models

Defined in `viral_editor.models` and serialized to `temp/*.json` between stages:

| Model | Purpose |
| :--- | :--- |
| `MediaInfo` | Probed stream metadata (duration, fps, resolution, codecs) |
| `Transient` | Audio hit at `{timestamp_ms, amplitude_normalized, type}` |
| `AudioTimeline` | BPM, duration, sample rate, and transient list |
| `SpeedSegment` | Output/source time window with constant speed factor |
| `FxEvent` | Zoom or rotation impulse keyed to a timestamp |
| `TeaserSpec` | Tail-clip teaser window and mask style |
| `TitleSpec` | Hook text layout, colors, and overlay window |
| `RenderPlan` | Aggregate plan handed to the FFmpeg builder |

## Development

```powershell
pytest
```

## Phased implementation

See [Documentation/plans/README.md](Documentation/plans/README.md) for the full phase breakdown. Phase 0 delivers scaffolding only; video logic begins in Phase 1.
