---
name: Phase 6 Render Plan Rewrite
overview: Rewrite Documentation/plans/phase-6-render.md so it reflects the codebase as it actually exists today (video/ package, existing proxy_render.py, RenderConfig, models.py), locks in the shared-builder refactor + deferred-title decisions, and defines a strict TDD-driven implementation sequence for the follow-up build.
todos: []
isProject: false
---


# Rewrite `Documentation/plans/phase-6-render.md`

## Why the current plan is stale

The existing doc (`Documentation/plans/phase-6-render.md`) describes a brand-new `render/ffmpeg_builder.py` + `render/renderer.py` package. That doesn't match reality:

- There is no `render/` package. All FFmpeg logic lives under [`src/viral_editor/video/`](src/viral_editor/video/) (`proxy_render.py`, `teaser.py`, `spatial_fx.py`, `speed_ramp.py`, `clip_reel.py`, `speed_presets.py`).
- [`src/viral_editor/video/proxy_render.py`](src/viral_editor/video/proxy_render.py) already implements ~90% of "Phase 6": per-segment `trim`/`setpts`/scale-crop chains, teaser tail extraction + mask, beat-synced zoom/rotate/pan FX chain, hook `drawtext` overlay, multi-clip `concat`/`xfade` composite, and `run_ffmpeg` orchestration — just tuned for a **360x640 preview** (`ultrafast`, `crf 28`, no locked encode).
- [`RenderConfig`](src/viral_editor/config.py) already holds the locked encode spec (`1080x1920`, `60fps`, `libx264`/`aac`, `crf 18`, `preset medium`) — the old plan's "Encode settings (locked)" section duplicates this instead of citing it.
- [`RenderPlan`](src/viral_editor/models.py) (aggregate: `speed_segments`, `teaser`, `fx_events`, `title`) is already defined in `models.py` but unused — it's the natural input contract for the final renderer.
- Phase 5 (title/hook-text overlay planner, `plan_title` -> `TitleSpec`) is **not implemented anywhere** — only the `TitleSpec` pydantic model exists. The old plan assumed it as a hard dependency.
- `pipeline.py` currently stops after the `teaser` stage; `title` and `render` stages are explicitly marked `skip` ("Not yet implemented (Phases 4-6)... Full wiring lands in Phase 7"). Wiring the pipeline end-to-end is out of scope for Phase 6 itself.
- Existing tests ([`tests/test_proxy_render.py`](tests/test_proxy_render.py)) already follow the "assert on generated filtergraph strings, no ffmpeg execution" pattern the old plan proposed — that convention is correct and will carry over.

## Confirmed decisions (from clarifying questions)

1. **Architecture:** Refactor `proxy_render.py` into shared, pure filter-chain builders parameterized by resolution/encode settings, reused by *both* the existing low-res preview and the new final render — instead of a separate duplicate `render/` package.
2. **Title dependency:** Defer title burning. The final renderer accepts an optional `TitleSpec` (and/or a pre-rendered ASS file path); when absent, it renders without a title overlay. Wiring real title planning is left to Phase 5 as a follow-up, referenced but not implemented here.

## New document structure for `phase-6-render.md`

Rewrite in place (same filename, keeps the phase index in `Documentation/plans/README.md` valid), with these sections:

1. **Goal / Status** — unchanged intent, but status notes: "supersedes the UI preview path in `video/proxy_render.py`; extracted shared builders now serve both."
2. **Current-state summary** — short callout of what already exists (`proxy_render.py`, `RenderConfig`, `RenderPlan`, `SpeedSegment`/`TeaserSpec`/`FxEvent`/`TitleSpec` models) so the plan reads as an extension, not greenfield work.
3. **Target module layout** (replaces `render/ffmpeg_builder.py` + `render/renderer.py`):
   - `src/viral_editor/video/filter_builders.py` — new home for the **pure** filter-chain builders extracted from `proxy_render.py` (segment trim/setpts/visual chain, teaser chain, spatial-fx chain, hook drawtext, concat/xfade assembly), each parameterized by `width/height` and no longer hardcoded to preview scale. Both preview and final renderers import from here.
   - `src/viral_editor/video/proxy_render.py` — slimmed down to preview-specific glue (360x640, `ultrafast`/`crf 28`) calling into `filter_builders.py`. Public API unchanged so `tests/test_proxy_render.py` keeps passing.
   - `src/viral_editor/video/final_render.py` (new) — the Phase 6 deliverable: builds the full filtergraph via `filter_builders.py` at `RenderConfig.width/height`, muxes music, encodes at the locked spec, and verifies output via `ffprobe`. Mirrors `render_composite`'s call shape (`segments`, `transitions`, `clip_paths`, `fx_events`, teaser, optional title) but targets `RenderConfig`.
   - `RenderPlan` (already in `models.py`) becomes the typed input struct `final_render.render_final(plan: RenderPlan, render_cfg: RenderConfig, clip_paths, audio_path, out_path, ...)` accepts, avoiding another bespoke parameter surface.
4. **Encode settings** — cite `RenderConfig` directly instead of restating a hardcoded block; note CFR-force, `+faststart`, cover-crop vs pad as today's `_visual_filters` already implements.
5. **FFmpeg technique notes** — trimmed to only what's new/different from the existing preview implementation (real resolution scale, final encode flags, ffprobe verification, deferred title hook point).
6. **Title overlay hook point** — explicit note: `final_render.py` takes `title: TitleSpec | None = None` (or `title_ass_path: Path | None`); when `None`, no overlay filter is inserted. Phase 5 will supply the real value later.
7. **Testing (TDD-explicit)** — replace the old generic bullet list with a concrete red-green sequence:
   - Extraction step: move existing `proxy_render.py` filter-chain tests to target `filter_builders.py` (refactor only, verified green before any new code).
   - New failing tests first, one at a time, in `tests/test_final_render.py`: (a) full-res builder emits `scale=1080:1920`-class output for a locked `RenderConfig`, (b) encode arg list contains `-crf 18 -preset medium -pix_fmt yuv420p -r 60 -c:a aac -b:a 192k -movflags +faststart`, (c) segment continuity (summed durations match plan), (d) title-absent path omits any `drawtext`/`ass` filter, (e) optional smoke test gated by `ffmpeg_available()` (skip like `test_ffmpeg_env.py` does) that renders a tiny fixture and `ffprobe`-verifies resolution/fps/codecs.
   - Each test run to failure and captured before writing minimal implementation, per the `/tdd` skill.
8. **Dependencies** — `filter_builders.py`, `utils/ffmpeg.py`, `RenderConfig`, `RenderPlan`/`SpeedSegment`/`TeaserSpec`/`FxEvent`/`TitleSpec` (all already in `models.py`).
9. **Acceptance criteria** — same intent (playable locked-spec MP4, FX land, duration matches music) but scoped to calling `final_render.render_final(...)` directly / via a thin CLI smoke path, not full pipeline wiring (that remains Phase 7's job, matching `pipeline.py`'s existing `# Full wiring lands in Phase 7` comment).
10. **Risks & mitigations** — keep filtergraph-escaping, quality-loss, slow-render, A/V-drift risks; add a new risk: "Preview/final code drift" mitigated by the shared `filter_builders.py` extraction being the single source of truth.

## Follow-up implementation plan (once this doc update is approved and we leave Plan Mode)

Strict TDD, one behavior at a time, per the attached `/tdd` skill:

1. Baseline: activate `.venv`, run `python -m pytest tests/test_proxy_render.py -v` to confirm current green state before touching anything.
2. Refactor phase (no behavior change): extract pure builders from `proxy_render.py` into `video/filter_builders.py`; rerun the full existing suite to confirm zero regressions before adding anything new.
3. Red/Green loop for `final_render.py`, one test at a time (write failing test -> run pytest, capture failure -> minimal implementation -> rerun green -> refactor):
   - Locked-resolution filtergraph shape
   - Locked encode arg list
   - Segment continuity assertion
   - Title-absent no-op path
   - `ffprobe`-gated smoke render (skipped when ffmpeg missing, same pattern as `test_ffmpeg_env.py`)
4. Update `Documentation/plans/README.md`'s pipeline diagram/table only if the module layout changes what it references (module path only — table already says "Core").

## Todos for this planning turn

- Rewrite `Documentation/plans/phase-6-render.md` with the structure above.
- No code changes yet (Plan Mode) — code refactor/TDD implementation happens after user confirms and we switch to Agent Mode.
</plan>
<parameter name="todos">[{"id": "rewrite-doc", "content": "Rewrite Documentation/plans/phase-6-render.md to match current codebase architecture (video/ package, filter_builders.py extraction, RenderConfig/RenderPlan reuse, deferred title, TDD-explicit testing section)"}, {"id": "switch-agent-mode", "content": "After doc is confirmed, switch to Agent Mode to begin the TDD refactor/implementation sequence"}, {"id": "baseline-tests", "content": "Activate .venv and run existing test_proxy_render.py suite as TDD baseline before any refactor"}, {"id": "extract-filter-builders", "content": "Refactor proxy_render.py pure filter-chain builders into video/filter_builders.py with zero behavior change, verified by rerunning full suite green"}, {"id": "tdd-final-render", "content": "Implement video/final_render.py one failing test at a time per /tdd skill (resolution, encode flags, continuity, title-absent, ffprobe smoke)"}]