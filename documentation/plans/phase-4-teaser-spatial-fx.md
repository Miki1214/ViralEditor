# Phase 4 - Teaser Inversion & Spatial FX Planner

**Goal:** Build the Frame-0 teaser clip spec (last 5% of footage, masked, prepended) and translate transients into `FxEvent`s (zoom punch + rotation shake) for the renderer.

**Status:** Core. Depends on [Phase 1](phase-1-config-ingestion.md), [Phase 2](phase-2-audio-dsp.md).

---

## Objective

Two related planners, both pure (no FFmpeg here - they emit specs/events that Phase 6 turns into filters):

1. **Teaser inversion** (Hook/Pattern-Interrupt core): isolate the completed "money shot" tail and prepend it as a curiosity hook.
2. **Spatial FX**: map transients to frame-level zoom and rotation impulses synced to the beat.

## Part A - Teaser builder

### Contract
- Input: video `MediaInfo`, `TeaserConfig` (`tail_fraction=0.05`, `duration_s=2.5`, `mask`).
- Output: `TeaserSpec`:
```json
{ "src_start_s": 28.5, "src_end_s": 30.0, "out_duration_s": 2.5, "mask": "vignette" }
```

### Design
- `src_start_s = src_duration_s * (1 - tail_fraction)`, `src_end_s = src_duration_s`.
- The tail (length = `tail_fraction * src_duration_s`) is time-fit to `out_duration_s` (typically slowed/stretched to fill ~2.5 s) via its own `setpts`.
- **Mask options** (applied in Phase 6, chosen here):
  - `vignette` - FFmpeg `vignette` filter for a soft darkened edge.
  - `dir_blur` - directional blur via `gblur`/`boxblur` to obscure detail while showing the finished state.
- The teaser is a **separate prepended clip** concatenated before the speed-ramped body (see [Phase 3](phase-3-speed-ramp.md) boundary note). Output timeline becomes `[teaser (0..2.5s)] + [body]`; the music plays continuously underneath both.
- The title overlay ([Phase 5](phase-5-title-overlay.md)) is composited over this teaser window.

> Design decision to confirm during build: does the music start at `t=0` over the teaser, or does the teaser sit "before" the musical body? Default: **music plays from t=0 across the teaser** (continuous track), so total output = music duration and the teaser eats the first 2.5 s of the body budget. Document whichever is chosen in one place.

## Part B - Spatial FX planner

### Contract
- Input: `AudioTimeline` transients, video `MediaInfo` (`fps`).
- Output: `list[FxEvent]`:
```json
{ "timestamp_s": 4.72, "kind": "zoom", "magnitude": 1.07, "decay_frames": 4 }
{ "timestamp_s": 4.72, "kind": "rotate", "magnitude": 1.2, "decay_frames": 4 }
```

### Design
- **Zoom punch:** for major transients (high amplitude / `drop`), scale `1.05`-`1.08` at the exact transient frame, then exponential decay back to `1.00` over `~4` frames. `magnitude` scales with normalized amplitude.
- **Rotation shake:** for `bass`-classified transients, apply a small rotation in `[-1.5deg, +1.5deg]` with the same short decay. Sign can alternate or be seeded-random for variety (use `seed` for determinism).
- Map each event's `timestamp_s` onto the **output timeline** (post speed-ramp). Because the body is time-warped, FX must be placed using the audio/output clock (transients are already in audio time), which is exactly the output clock - so no remapping needed for the body, but offset by the teaser duration if the teaser shifts the body.
- Emit decay as either discrete per-frame keyframes or as parameters for an expression-based filter (Phase 6 decides; planner just provides magnitude + decay length).

### Determinism
Any randomization (rotation direction/jitter) is driven by `JobConfig.seed`.

## Pure-function shapes

```python
def build_teaser_spec(media: MediaInfo, config: TeaserConfig) -> TeaserSpec: ...
def plan_spatial_fx(timeline: AudioTimeline, media: MediaInfo, *, seed: int) -> list[FxEvent]: ...
```

Pipeline writes `temp/teaser_spec.json` and `temp/fx_events.json`.

## Dependencies

- Transients + classifications from [Phase 2](phase-2-audio-dsp.md).
- `MediaInfo` from [Phase 1](phase-1-config-ingestion.md).
- Coordinates output-clock placement with [Phase 3](phase-3-speed-ramp.md) (teaser offset).

## Testing

- Teaser: tail range math correct for various `tail_fraction`; `out_duration_s` respected.
- FX: every `drop` produces a `zoom` event; every `bass` produces a `rotate` event within magnitude bounds.
- Decay length and magnitude scale with amplitude.
- Determinism with fixed seed.

## Acceptance criteria

- `TeaserSpec` references the correct tail of the sample video.
- `FxEvent` list aligns timestamps to transients and stays within magnitude limits.
- Artifacts inspectable in `temp/`.

## Risks & mitigations

- **Zoom revealing black borders on rotate:** Phase 6 must over-scale slightly (e.g., base scale 1.02) before rotate/crop so rotation never shows edges.
- **FX overload on dense transients:** cap events per second; merge events within a small window.
- **Teaser/body timing ambiguity:** resolve the single "does music cover teaser" decision early and encode it in `output_duration_s` accounting.
