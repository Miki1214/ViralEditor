# Phase 3 - Dynamic Speed-Ramp Planner

**Goal:** Produce a deterministic list of `SpeedSegment`s that map the timelapse footage onto the music timeline - accelerating during build-ups and snapping to slow-motion on drops.

**Status:** Core, and the hardest/most important module. Depends on [Phase 1](phase-1-config-ingestion.md), [Phase 2](phase-2-audio-dsp.md).

---

## Objective

Implement the math that turns the audio energy envelope into a **piecewise-constant playback-speed plan**. The plan is the bridge between "music time" (fixed, the output clock) and "source video time" (consumed at variable rates). This module is pure math; rendering happens in [Phase 6](phase-6-render.md).

## Why segments (not a continuous curve)

FFmpeg's `setpts` cannot smoothly evaluate an arbitrary continuous speed curve across a stream in one pass. The robust, frame-accurate approach is to discretize the output timeline into segments of constant speed, extract the matching source range per segment (`trim` + `setpts`), and concat them. Therefore the planner's job is to emit clean, gapless segments.

## Contract

### Input
- `AudioTimeline` (Phase 2): transients + onset envelope.
- Video `MediaInfo` (Phase 1): `src_duration_s`, `fps`.
- `output_duration_s` = music duration.
- `SpeedRampConfig`: `s_min`, `s_max`, `alpha`.

### Output: `list[SpeedSegment]`
Each segment is gapless on the output axis and references a source range:
```json
{ "out_start_s": 4.50, "out_end_s": 4.90, "src_start_s": 30.10, "src_end_s": 30.50, "speed_factor": 1.0 }
```
Invariant: `segments` tile `[0, output_duration_s]` with no gaps/overlaps; `src` ranges are monotonically increasing.

## Detailed design

### 1. Build the speed function R(t)
From the onset strength envelope `E(t)` (normalized to `[0,1]`), define playback speed on the output clock:

```
R(t) = clamp( s_max - E(t) * alpha, s_min, s_max )
```

- High energy (build-ups) -> `R(t)` near `s_max` (footage flashes forward).
- On transients flagged `drop` -> force `R(t) = s_min` for a short window (e.g., 200-400 ms) to create the satisfying stabilization on the beat.
- `alpha` controls sensitivity; with `alpha=0` the system runs at a constant `s_max` (useful baseline/debug).

> Note: a higher `R` means *more source seconds consumed per output second* (fast-forward). Be explicit and consistent about this convention in code and docstrings.

### 2. Discretize into segments
- Choose segment boundaries at a fixed grid (e.g., every beat from BPM, or fixed `step_ms = 100`) plus forced boundaries around each `drop` window.
- For each output segment `[out_start, out_end]`, take a representative speed (mean of `R(t)` over the segment, snapped to a small set of discrete factors to limit re-encode churn, e.g., quantize to 0.5x steps).
- Consume source footage: `src_len = speed_factor * (out_end - out_start)`. Advance a `src_cursor`; set `src_start = cursor`, `src_end = cursor + src_len`.

### 3. Fit source footage to the music (the budget problem)
Total source consumed = `sum(speed_factor_i * out_len_i)`. This generally will NOT equal `src_duration_s`. Resolve with a documented policy (config-selectable, default = `scale`):
- **`scale` (default):** after building raw segments, compute `scale = src_duration_s / total_src_consumed` and multiply every `speed_factor` by it (then re-clamp softly). Guarantees the footage starts at 0 and ends at the last frame exactly on the final beat. Preserves *relative* dynamics (fast stays faster than slow).
- **`loop`:** if footage is shorter than needed even at `s_min`, wrap the source cursor (modulo `src_duration_s`) and mark looped segments so Phase 6 can re-seek.
- **`trim`:** consume linearly and accept ending early/late (debug only).

Account for the teaser: the teaser (Phase 4) consumes the last `tail_fraction` of source and a fixed output window; the planner either reserves that output window or treats the teaser as a separate prepended clip (default: **teaser is a separate prepended clip**, so the ramp planner owns only the post-teaser body). Document this boundary clearly since it affects total durations.

### 4. Frame alignment
Snap all `out_*` boundaries to whole output frames (`1/fps`) to avoid sub-frame concat artifacts. Snap `src_*` to source frame boundaries.

## Pure-function shape

```python
def plan_speed_segments(
    timeline: AudioTimeline,
    media: MediaInfo,
    output_duration_s: float,
    config: SpeedRampConfig,
) -> list[SpeedSegment]: ...
```

No I/O. Returns segments; pipeline writes `temp/speed_segments.json`.

## Dependencies

- Onset envelope from [Phase 2](phase-2-audio-dsp.md) (reuse `temp/onset_envelope.npy` to avoid recompute).
- Video `MediaInfo` from [Phase 1](phase-1-config-ingestion.md).

## Testing

- **Tiling invariant:** segments cover `[0, output_duration_s]` exactly, no gaps/overlaps (property test).
- **Monotonic source:** `src_end_i <= src_start_{i+1}` for non-looped policy.
- **Budget under `scale`:** total consumed source ~= `src_duration_s` within one frame.
- **Drop behavior:** a `drop` transient yields a `speed_factor == s_min` segment at that timestamp.
- **Edge cases:** very short source (forces `loop`); source longer than needed (high speeds).

## Acceptance criteria

- For the sample assets, produces a gapless segment list whose summed output length equals the music duration and whose source consumption matches the footage under the default `scale` policy.
- Drops visibly map to slow segments.
- `temp/speed_segments.json` is human-inspectable.

## Risks & mitigations

- **Choppiness from too many tiny segments:** quantize speeds and enforce a `min_segment_ms`.
- **Extreme speeds dropping too many frames:** clamp `s_max` and warn when footage is far too short/long for the music.
- **Off-by-one frame drift accumulating over many segments:** carry fractional remainder forward (accumulate in float, snap on output) rather than rounding each segment independently.
