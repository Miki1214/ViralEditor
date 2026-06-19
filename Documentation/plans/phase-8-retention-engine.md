# Phase 8 - Retention Engine (Deferred)

**Goal:** Layer the watch-time features on top of the working core loop: kinetic captions, a progress indicator, and the infinite loop wrap.

**Status:** Deferred (wanted eventually). Depends on the completed core loop (Phases [0](phase-0-scaffolding.md)-[7](phase-7-cli-e2e.md)).

---

## Objective

Add the retention-optimization features from section 2.4 of the [high-level plan](../automated_retention_video_editor_plan.md). Each is an additive, independently shippable module that slots into the existing planner -> render contract.

## Sub-modules

### 8.1 Kinetic captions (Whisper ASR)
- New input: optional voiceover track (or reuse the music track if it contains speech - usually not). For v1 of this phase, assume an optional `voiceover_path` in `JobConfig`.
- `audio/transcribe.py`: run `openai-whisper` (or `faster-whisper` for speed) with **word-level timestamps** -> `CaptionTimeline` (word, start_ms, end_ms).
- `overlay/captions.py`: group words into 1-3 word blocks; mark the active word (scale +15%, color shift) per the plan; emit an ASS subtitle with per-word karaoke-style timing.
- Render: burn the captions ASS in the assembly pass ([Phase 6](phase-6-render.md) builder gains a captions input).
- New dep: `openai-whisper` or `faster-whisper` (note: pulls in PyTorch; document install size and optional GPU).

### 8.2 Progress indicator
- `overlay/progress_bar.py`: emit a `ProgressBarSpec` (height 4px, bottom of safe zone, `0%`->`100%` linear over `output_duration_s`).
- Render via a time-keyed `drawbox` whose width scales with `t/output_duration_s`. Pure planner + builder addition; no new deps.

### 8.3 Infinite loop wrap
- `video/loop_wrap.py`: plan a final 1.5 s opacity crossfade (`0->1`) between the closing frames and a duplicate of the opening asset sequence (`xfade`/`blend` in FFmpeg).
- Audio seamless loop: analyze waveform cross-points to choose a loop seam with minimal level discontinuity; apply a short equal-power crossfade (`acrossfade`).
- Render additions in the assembly pass.

## Sequencing

Recommended order once core loop is stable: **8.2 (cheapest)** -> **8.3** -> **8.1 (heaviest, new big dep)**. Each can ship independently behind a config flag (`features.captions`, `features.progress_bar`, `features.loop_wrap`).

## Testing

- Captions: word-timing fixture -> assert block grouping and active-word transitions; ASS validity.
- Progress bar: width at `t=0`, mid, end equals expected px.
- Loop wrap: output duration extends by wrap length; audio seam has no click (energy continuity check).

## Acceptance criteria

- Each feature toggles independently via config and renders correctly without regressing the core loop.

## Risks & mitigations

- **Whisper install weight / runtime:** prefer `faster-whisper`; make captions strictly opt-in.
- **Caption sync drift over time-warped body:** captions follow voiceover/audio clock (the output clock), so they remain aligned; verify against the teaser offset.
