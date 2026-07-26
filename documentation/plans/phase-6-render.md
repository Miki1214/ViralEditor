# Phase 6 — Final Render (FFmpeg Graph Builder & Encoder)

**Goal:** Consume all stage artifacts (`SpeedSegment`s, `TeaserSpec`, `FxEvent`s, optional `TitleSpec`) and produce the final `1080×1920 / 60 fps / H.264+AAC` MP4.

**Status:** Core. Supersedes the low-res UI preview path in [`src/viral_editor/video/proxy_render.py`](../../src/viral_editor/video/proxy_render.py); extracted shared builders serve **both** preview and final render.

**Depends on:** Phases [3](phase-3-speed-ramp.md), [4](phase-4-teaser-spatial-fx.md). Phase [5](phase-5-title-overlay.md) title burning is **optional** — renderer accepts `TitleSpec | None` and renders without overlay when absent.

**Out of scope:** Full pipeline wiring (`pipeline.py` render stage) lands in [Phase 7](phase-7-cli-e2e.md).

---

## Current state (what already exists)

| Asset | Location | Role |
| :--- | :--- | :--- |
| Preview FFmpeg graph + orchestration | [`video/proxy_render.py`](../../src/viral_editor/video/proxy_render.py) | ~90% of Phase 6 logic: segment `trim`/`setpts`, scale/crop, teaser mask, spatial FX, hook `drawtext`, multi-clip `concat`/`xfade`, `run_ffmpeg` — tuned for **360×640**, `ultrafast`/`crf 28` |
| Locked encode spec | [`RenderConfig`](../../src/viral_editor/config.py) | `1080×1920`, `60 fps`, `libx264`/`aac`, `crf 18`, `preset medium`, `yuv420p` |
| Aggregate render input | [`RenderPlan`](../../src/viral_editor/models.py) | `speed_segments`, `teaser`, `fx_events`, `title` — defined but not yet consumed |
| Domain models | [`models.py`](../../src/viral_editor/models.py) | `SpeedSegment`, `TeaserSpec`, `FxEvent`, `TitleSpec` |
| FFmpeg boundary | [`utils/ffmpeg.py`](../../src/viral_editor/utils/ffmpeg.py) | `run_ffmpeg`, `run_ffprobe_json`, `escape_filter_path`, `resolve_drawtext_fontfile` |
| Builder unit tests | [`tests/test_proxy_render.py`](../../tests/test_proxy_render.py) | Assert on generated filtergraph strings (no FFmpeg execution) |

Phase 5 (`plan_title` → `TitleSpec`) is **not implemented** — only the `TitleSpec` pydantic model exists. Title integration is a documented hook point, not a blocker.

---

## Objective

Translate pure planner artifacts into FFmpeg work and encode the output. Concentrate all FFmpeg filter knowledge behind **shared, testable builders** so planners stay engine-agnostic.

## Strategy: single-pass `filter_complex` (matches existing preview)

The preview renderer already uses an in-memory `filter_complex` graph (per-segment `trim`/`setpts` chains → `concat`/`xfade` → spatial FX). Phase 6 **reuses that architecture** at full resolution instead of introducing per-segment intermediate files.

```
[clip inputs] ──► trim/setpts/scale per SpeedSegment ──► concat|xfade ──► spatial FX ──► [optional title] ──► encode
                                                                                              ▲
[music input] ───────────────────────────────────────────────────────────────────────────── mux ┘
```

> **Why not segment-extract-then-concat?** Intermediate files aid debugging but duplicate logic already proven in `proxy_render.py`. A shared `filter_builders.py` is the single source of truth; add intermediate-file mode later only if single-pass graphs prove too brittle at 1080p.

---

## Target module layout

Replaces the old `render/ffmpeg_builder.py` + `render/renderer.py` proposal. All code stays under `src/viral_editor/video/`.

### `video/filter_builders.py` (new — extracted)

Pure filter-chain builders (no `run_ffmpeg`). Extracted from `proxy_render.py`:

| Builder | Responsibility |
| :--- | :--- |
| `segment_filter_chains(...)` | `trim` → `setpts` → visual (scale/crop/pad, rotation, spatial crop) → duration trim |
| `build_teaser_filter_chain(...)` | Tail extract, time-fit, mask (`vignette` / `gblur`) |
| `apply_spatial_fx_chain(...)` | Beat-synced zoom / rotate / pan with linear decay |
| `drawtext_hook_overlay(...)` | Simple hook text (preview + fallback) |
| `build_composite_filtergraph(...)` | Multi-slot storyboard assembly with `concat`/`xfade` |
| `composite_output_duration_s(...)` | Output length estimate for mux `-t` |

Each builder takes explicit `width`/`height` (and `fps` where needed) — **not** hardcoded to preview scale.

### `video/proxy_render.py` (slimmed)

Preview-specific glue only:

- Default scale `(360, 640)`, `ultrafast`/`crf 28`, preview FX gain constants.
- Imports builders from `filter_builders.py`.
- **Public API unchanged** — `tests/test_proxy_render.py` must keep passing.

### `video/final_render.py` (new — Phase 6 deliverable)

Final encode orchestrator:

```python
def render_final(
    plan: RenderPlan,
    render_cfg: RenderConfig,
    *,
    clip_paths: dict[str, Path],
    clip_durations: dict[str, float],
    audio_path: Path,
    out_path: Path,
    music_start_s: float | None = None,
    music_end_s: float | None = None,
    transitions: list[str] | None = None,
    clip_transforms: dict[str, tuple[int, str, tuple[float, float, float, float] | None]] | None = None,
    segment_transforms: list[tuple[int, str, tuple[float, float, float, float] | None]] | None = None,
    segment_roles: list[str] | None = None,
    hook_start_mask: str | None = None,
    fx_seed: int = 42,
    fx_intensity: float = 1.0,
    title: TitleSpec | None = None,
    title_ass_path: Path | None = None,
    temp_dir: Path | None = None,
) -> Path: ...
```

- Builds filtergraph via `filter_builders.py` at `render_cfg.width` × `render_cfg.height`.
- Muxes looped/trimmed music (reuses `ensure_loop_seam_audio` pattern from preview).
- Encodes with `RenderConfig` values + `-movflags +faststart`, `-vsync cfr`.
- Verifies output via `ffprobe` (resolution, fps, codecs, duration ≈ plan).

`RenderPlan` is the typed input — avoids a bespoke parameter surface per stage artifact.

### Title overlay hook point (deferred)

- `title: TitleSpec | None = None` — when `None`, no `drawtext`/`ass` filter is inserted.
- `title_ass_path: Path | None = None` — when set, burns pre-rendered ASS (Phase 5 output).
- Phase 5 (`plan_title`) supplies real values later; Phase 6 tests the absent-title path explicitly.

---

## Encode settings

Sourced from [`RenderConfig`](../../src/viral_editor/config.py) — do not hardcode elsewhere:

| Field | Default | FFmpeg flag |
| :--- | :--- | :--- |
| `width` / `height` | `1080` / `1920` | filtergraph `scale`/`crop` target |
| `fps` | `60` | `-r 60 -vsync cfr` |
| `vcodec` | `libx264` | `-c:v libx264` |
| `acodec` | `aac` | `-c:a aac` |
| `crf` | `18` | `-crf 18` |
| `preset` | `medium` | `-preset medium` |
| `pix_fmt` | `yuv420p` | `-pix_fmt yuv420p` |

Additional flags (not on `RenderConfig`, applied in `final_render.py`):

- `-b:a 192k` — audio bitrate
- `-movflags +faststart` — streaming-friendly MP4
- Scale strategy: `cover` mode (`scale` to fill → `crop`) via existing `_visual_filters`; `contain` uses `pad`

Audio is the untouched music track muxed once at assembly — never speed-adjusted per segment.

---

## FFmpeg technique notes (delta from preview)

| Concern | Preview (`proxy_render`) | Final (`final_render`) |
| :--- | :--- | :--- |
| Resolution | `360×640` | `RenderConfig.width×height` |
| Encode | `ultrafast`, `crf 28` | `preset medium`, `crf 18` |
| FX gain | `PREVIEW_ROTATE_GAIN`, `PREVIEW_PAN_GAIN` boosted | Production magnitudes (intensity from `SpatialFxConfig`) |
| CFR | `COMPOSITE_FPS = 30` internal normalize | `render_cfg.fps` (60) end-to-end |
| Verification | None | `ffprobe` resolution/fps/codec/duration check |
| Title | `drawtext` hook only | Optional `TitleSpec` / ASS path |

Shared behavior (unchanged):

- **Speed:** `setpts=PTS/${speed_factor}` on video; music muxed at assembly.
- **Zoom punch:** time-keyed `scale`/`crop` with linear decay over `decay_frames/fps`.
- **Rotation:** `rotate=a=...` with decay; pan uses headroom pre-scale.
- **Teaser:** prepended via separate filter chain or `hook_start` slot role + mask.
- **Concat:** `concat` filter for cuts; `xfade` for transitions.

---

## Dependencies

- Upstream artifacts: `SpeedRampPlan.segments`, `TeaserSpec`, `list[FxEvent]`, optional `TitleSpec`.
- [`video/filter_builders.py`](../../src/viral_editor/video/filter_builders.py) — shared pure builders.
- [`utils/ffmpeg.py`](../../src/viral_editor/utils/ffmpeg.py) — subprocess boundary.
- [`RenderConfig`](../../src/viral_editor/config.py), [`RenderPlan`](../../src/viral_editor/models.py).

---

## Testing (strict TDD)

Follow the `/tdd` skill: **one failing test → minimal implementation → green → refactor**. Activate venv before every run:

```powershell
& c:/Sources/ViralAutomation/.venv/Scripts/Activate.ps1
python -m pytest tests/... -v
```

### Phase A — Baseline (before any edits)

```powershell
python -m pytest tests/test_proxy_render.py -v
```

Must be green. This is the regression anchor.

### Phase B — Extract `filter_builders.py` (refactor only, no new behavior)

1. Move pure builders from `proxy_render.py` → `filter_builders.py`.
2. `proxy_render.py` re-exports / imports from `filter_builders`.
3. Rerun `tests/test_proxy_render.py` — must stay green.
4. Optionally add `tests/test_filter_builders.py` that imports builders directly (same assertions, clearer ownership).

### Phase C — `final_render.py` (one test at a time)

New file: `tests/test_final_render.py`. Write **exactly one** test per cycle; run pytest and capture the failure before implementing.

| # | Test | Asserts |
| :--- | :--- | :--- |
| 1 | `test_final_filtergraph_uses_render_config_resolution` | Graph contains `scale=1080:1920` (or `crop=1080:1920`) for default `RenderConfig` |
| 2 | `test_final_encode_args_locked_spec` | Command list includes `-crf 18 -preset medium -pix_fmt yuv420p -r 60 -c:a aac -b:a 192k -movflags +faststart` |
| 3 | `test_final_segment_continuity` | Summed segment `out_end_s - out_start_s` matches `RenderPlan.output_duration_s` (±1 frame) |
| 4 | `test_final_render_without_title_omits_overlay` | Filtergraph has no `drawtext` or `ass=` when `title=None` and `title_ass_path=None` |
| 5 | `test_final_render_smoke_ffprobe` | Gated: `pytest.skip` when `not ffmpeg_available()`. Render tiny fixture; `ffprobe` confirms `1080×1920`, `60 fps`, `h264`/`aac`, duration ≈ music |

Forbidden: writing test + implementation in the same turn; assuming pass/fail without terminal output.

### Phase D — Refactor pass

Once all green, clean up `final_render.py` for single-responsibility. Rerun full module suite:

```powershell
python -m pytest tests/test_proxy_render.py tests/test_final_render.py -v
```

---

## Acceptance criteria

- `render_final(...)` produces a playable MP4 at the locked `RenderConfig` spec from sample assets.
- Speed changes and FX visibly land on beats; teaser appears in the first ~2.5 s.
- Output duration matches the music window within one frame.
- Title absent → render succeeds without overlay filters.
- Callable directly or via a thin CLI smoke path — **not** requiring full `pipeline.py` wiring (Phase 7).

---

## Risks & mitigations

| Risk | Mitigation |
| :--- | :--- |
| Filtergraph escaping (Windows paths, special chars) | Centralize in `filter_builders.py`; use `escape_filter_path`; prefer ASS files for multi-color title (Phase 5) |
| Preview/final code drift | Shared `filter_builders.py` is the single source of truth for all filter chains |
| Quality loss from re-encode | Single-pass `filter_complex` — encode once at `crf 18`; no intermediate segment files |
| Slow renders at 1080p60 | Start correct; tune `-preset` per job later; preview stays low-res |
| A/V drift | Mux audio once at assembly; never speed-adjust music; `-vsync cfr` |
| Missing title planner (Phase 5) | Optional `title` param; hook point documented; tests cover absent path |
