---
name: Multi-step auto-rotation on upload
overview: Add a 3-step auto-rotation detection pipeline (container metadata, width/height heuristic, local Ollama vision keyframe analysis) that silently sets rotation_deg on clip upload, with per-step logging for later tuning, while keeping the existing 90 degree manual override buttons as a safety net.
todos:
  - id: baseline
    content: Activate .venv and run existing auto_rotate-adjacent test baseline (test_models.py, test_api.py, test_proxy_render.py) to confirm a clean starting point
    status: completed
  - id: tdd_combine_votes
    content: "TDD one branch of combine_votes at a time (0/1/2/3-step cases, tie-break priority, no-2-match fallback): red test first, minimal green, refactor"
    status: completed
  - id: tdd_aspect
    content: TDD detect_aspect_rotation (landscape-vs-portrait, portrait-vs-portrait, square edge case)
    status: completed
  - id: tdd_metadata
    content: TDD detect_metadata_rotation against fixture ffprobe payloads with/without side_data_list/tags.rotate
    status: completed
  - id: tdd_vision
    content: "TDD detect_vision_rotation with a mocked httpx client: success, timeout-abstain, malformed-response-abstain"
    status: completed
  - id: settings
    content: "Add AutoRotateSettings (env-driven: AUTO_ROTATE_ENABLED, OLLAMA_HOST, OLLAMA_MODEL, OLLAMA_VISION_TIMEOUT_S, AUTO_ROTATE_KEYFRAME_COUNT) and document in README"
    status: completed
  - id: log_model
    content: Add AutoRotationLog domain model and JSON artifact writer under temp/rotation_log/<clip_id>.json, TDD'd against a run_auto_rotation test asserting the artifact contents
    status: completed
  - id: tdd_wire_create_job
    content: "TDD: failing API test asserting ClipInput.rotation_deg reflects detection in create_job, then wire run_auto_rotation into the clip loop"
    status: completed
  - id: tdd_wire_assign_slot_video
    content: "TDD: failing API tests for (a) auto-detected rotation applied when form omits rotation_deg, (b) explicit rotation_deg overrides detection, then wire assign_slot_video"
    status: completed
  - id: full_regression
    content: Run the full Python test suite once all units are green to catch regressions, then refactor for cleanup
    status: completed
isProject: false
---

# Multi-step auto-rotation on upload

## Voting algorithm (confirmed with user)

Each step returns either **no recommendation** (abstain) or `{rotate: bool, direction: "cw" | "ccw" | None}`.

1. **Metadata step** — read container rotation (`side_data_list` rotation / `tags.rotate`) via ffprobe. If present: exact direction + rotate flag. If absent: abstain.
2. **Width/height step** — compare probed `width`/`height` aspect against the job's target portrait aspect. Always returns `rotate: bool`, but **never** a direction (`direction=None`). It can corroborate any direction chosen by another step, but can't be the sole source of a direction match.
3. **Vision step (Ollama)** — extract a few evenly-spaced keyframes, ask a local Ollama vision model to judge orientation + confidence + direction. Abstains if Ollama is unreachable, times out, or the response can't be parsed confidently.

Combine, per user's spec:

- **0 non-abstaining steps** → `rotation_deg = 0`, log "no recommendation".
- **1 non-abstaining step** → follow it. If it's width/height alone and says `rotate=True` → default to **90 CW**.
- **2 non-abstaining steps** → if they agree (same `rotate` bool, and same direction whenever both have one) → apply. If they disagree → break the tie using priority **Width/Height > Metadata > Vision** (trust the higher-priority step's call).
- **3 non-abstaining steps** → need at least 2 to "match" (same `rotate` bool; width/height's vote counts as matching whatever direction the other matching step supplies, since it has none of its own). If at least 2 match → apply that outcome (direction from whichever matching step has one, defaulting to CW if none does). If no 2 match at all → do **not** auto-rotate (`rotation_deg` stays 0 / whatever came in), just log all three for review.
- Only 90 degree multiples are ever produced (0/90/180/270).

## New module: `src/viral_editor/video/auto_rotate.py`

- `RotationVote` domain model (`step: Literal["metadata","aspect","vision"]`, `rotate: bool | None`, `direction: Literal["cw","ccw"] | None`, `confidence: float | None`, `detail: str`).
- `detect_metadata_rotation(path) -> RotationVote | None` — new ffprobe call requesting `-show_entries stream_side_data=rotation:stream_tags=rotate` (or reuse/extend `probe_media`'s existing ffprobe payload in [src/viral_editor/ingest/loader.py](src/viral_editor/ingest/loader.py) to avoid a second subprocess call).
- `detect_aspect_rotation(media: MediaInfo, target_aspect: float) -> RotationVote` — pure width/height comparison, no probing needed since `MediaInfo.width/height` already exist.
- `detect_vision_rotation(path, media: MediaInfo, settings) -> RotationVote | None` — extract N keyframes with ffmpeg, call local Ollama (`httpx`, already a dependency) at `settings.ollama_host` with `settings.ollama_model`, short timeout, parse a structured response (rotation direction + confidence). Any failure/timeout → return `None` (abstain), never raise.
- `combine_votes(votes: list[RotationVote | None]) -> tuple[int, AutoRotationLog]` — implements the voting algorithm above; returns final `rotation_deg` plus a structured log object capturing every step's raw vote and the final decision + reasoning.
- `run_auto_rotation(path, media, *, target_aspect, settings, log_dir) -> int` — orchestrates the 3 steps synchronously (vision step wrapped with a timeout), writes the JSON log artifact, returns the resulting `rotation_deg`.

## Configuration

Add a small settings surface (not part of per-job `JobConfig`, since this is deployment/environment config the user wants to swap models on without touching job JSON):

- New `AutoRotateSettings` in [src/viral_editor/config.py](src/viral_editor/config.py) (or a small `auto_rotate_settings.py`), reading env vars with defaults:
  - `AUTO_ROTATE_ENABLED` (default `true`)
  - `OLLAMA_HOST` (default `http://localhost:11434`)
  - `OLLAMA_MODEL` (default `llava`)
  - `OLLAMA_VISION_TIMEOUT_S` (default `6`)
  - `AUTO_ROTATE_KEYFRAME_COUNT` (default `3`)
- Document these in README as easily overridable so multiple models can be tried.

## Logging for fine-tuning

- `AutoRotationLog` domain model in `models.py`: clip id/path, each step's raw vote (including abstains and why), final `rotation_deg`, timestamp.
- Written as `temp/rotation_log/<clip_id>.json` in the job workspace (mirrors existing debug-artifact pattern like storyboard segment debug rows).

## Wiring into upload endpoints

Both in [src/viral_editor/api/routes/jobs.py](src/viral_editor/api/routes/jobs.py):

1. **`create_job`** (multi-clip loop, ~line 210-228): after `save_upload` + implicit probe, call `run_auto_rotation(...)` and pass the resulting value into the `ClipInput(...)` construction's new `rotation_deg=` argument (field already exists on `ClipInput` but is currently never set here).
   - *Caveat to flag to the user in the summary*: today, `ClipInput.rotation_deg` from this multi-clip path isn't yet consumed by the reel/render filtergraph builder (only `StorySlot.rotation_deg`, set via the storyboard slot-assignment path, is wired through `filter_builders.py`). Auto-detecting and storing it on `ClipInput` is still correct and forward-compatible, but making it actually apply to the reel render is a separate, pre-existing wiring gap — call this out explicitly, not silently paper over it.
2. **`assign_slot_video`** (~line 974-1030): after `save_upload` + `probe_media`, call `run_auto_rotation(...)`. If the caller (UI) already sent an explicit `rotation_deg` in the form, that still wins (manual override always beats auto-detection); otherwise use the detected value instead of hardcoded `rotation_deg or 0`.

Both call sites: synchronous, with the vision step's own internal timeout (~6-8s) so a slow/unreachable Ollama server degrades gracefully to the 2-step (metadata + aspect) result rather than blocking the request indefinitely.

## Vision step detail (keyframe extraction + Ollama call)

- Extract `AUTO_ROTATE_KEYFRAME_COUNT` frames evenly spaced across the clip duration via ffmpeg (reuse `run_ffmpeg`/binary resolution helpers in [src/viral_editor/utils/ffmpeg.py](src/viral_editor/utils/ffmpeg.py)), written to a temp scratch dir, base64-encoded.
- Call Ollama's `/api/generate` (or `/api/chat`) with the model configured, one prompt per frame (or all frames in one multi-image prompt if the model supports it) asking specifically: "does this frame look rotated, and if so is it 90 CW or 90 CCW, plus a confidence 0-1".
- Aggregate multi-frame answers (majority vote across frames + average confidence) into a single `RotationVote`; treat low-confidence/inconsistent aggregate as abstain.

## UI

No required UI changes — the existing 90 degree left/right rotate buttons in [web/src/components/StoryboardPanel.tsx](web/src/components/StoryboardPanel.tsx) remain the correction mechanism. Optionally (not required) surface a small "auto-rotated" indicator, but keep scope minimal per the request ("we still expose 90 degree rotation on ui").

## Tests

- Unit tests for `combine_votes` covering every branch of the voting table (0/1/2/3 non-abstaining steps, agreement, disagreement, tie-break priority, no-2-match fallback).
- Unit test for `detect_aspect_rotation` (landscape source vs portrait target, and vice versa).
- Unit test for `detect_metadata_rotation` against a fixture ffprobe payload with/without `side_data_list`/`tags.rotate`.
- Vision step tests with a mocked `httpx` client (no real Ollama dependency in CI) covering success, timeout, and malformed-response abstain paths.
- API-level test in `tests/test_api.py` asserting `assign_slot_video` picks up an auto-detected rotation when the caller omits `rotation_deg`, and that an explicit `rotation_deg` in the form still overrides it.

## TDD execution protocol (/tdd)

This plan is implemented under a strict Red-Green-Refactor loop, per [.agents/skills/tdd/SKILL.md](.agents/skills/tdd/SKILL.md). No functional code is written without a preceding failing test.

1. **Phase 1 — Contextual impact mapping.** Before touching `auto_rotate.py` or the two upload endpoints, run the current baseline suite (activate the venv first, per workspace rule):

   ```powershell
   & c:/Sources/ViralAutomation/.venv/Scripts/Activate.ps1
   python -m pytest tests/test_models.py tests/test_api.py tests/test_proxy_render.py -v
   ```

   Confirm a clean/green baseline before any edits.

2. **Phase 2 — Red.** For each unit below, write exactly **one** isolated test with a descriptive name (e.g. `test_combine_votes_three_steps_two_match_uses_direction_from_metadata`), run it, and capture the real failure (`ModuleNotFoundError` / `AttributeError` / assertion mismatch) before writing any implementation:
   - `combine_votes` — one test per branch of the voting table (0/1/2/3 non-abstaining votes, agreement, tie-break priority `Width/Height > Metadata > Vision`, no-2-match fallback, 90-degree-multiple-only guarantee).
   - `detect_aspect_rotation` — landscape-vs-portrait-target, portrait-vs-portrait-target, square edge case.
   - `detect_metadata_rotation` — fixture ffprobe payload with `side_data_list` rotation, with legacy `tags.rotate`, and with neither (abstain).
   - `detect_vision_rotation` — mocked `httpx` client: confident single-direction response, low-confidence/inconsistent-frames abstain, timeout abstain, malformed JSON abstain.
   - `run_auto_rotation` — asserts the `temp/rotation_log/<clip_id>.json` artifact contains every step's vote plus the final decision.
   - API wiring — `assign_slot_video` auto-detects when `rotation_deg` is omitted from the form, and an explicit `rotation_deg` still overrides detection; `create_job` sets `ClipInput.rotation_deg` from detection.

3. **Phase 3 — Green.** Implement the minimal code to pass each freshly-red test (no speculative extra branches, no unrelated helpers). Re-run that single test file/case; if it fails, roll back and try a structurally different minimal fix rather than layering guesses.

4. **Phase 4 — Refactor.** Once a unit is green, clean up naming/structure, then re-run the whole module's test file to check for regressions before moving to the next unit in the todo list.

5. Commit atomically per unit (e.g. `feat(auto-rotate): pass combine_votes voting table tests`), never bundling a new test with unrelated implementation in the same commit — matching this repo's fix-forward, no-revert convention.

## Todos
