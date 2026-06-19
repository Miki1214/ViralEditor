# Phase 6 - FFmpeg Graph Builder & Renderer

**Goal:** Consume all stage artifacts (speed segments, teaser spec, FX events, title spec) and produce the final `1080x1920 / 60fps / H.264+AAC` MP4.

**Status:** Core. Depends on Phases [3](phase-3-speed-ramp.md), [4](phase-4-teaser-spatial-fx.md), [5](phase-5-title-overlay.md).

---

## Objective

Translate the pure plans into actual FFmpeg work and encode the output. Concentrate all FFmpeg knowledge here behind a small, testable builder so planners stay engine-agnostic.

## Strategy: segment-extract-then-concat (chosen over one mega-graph)

A single giant `filter_complex` for variable speed + FX + teaser + overlay is brittle and hard to debug. The plan uses a **two-stage approach**:

1. **Per-segment clip extraction** (the body): for each `SpeedSegment`, run an FFmpeg job that `trim`s the source range, applies `setpts=PTS/speed_factor`, scales/pads to `1080x1920`, and writes an intermediate clip to `temp/segments/NNN.mp4` (or use the `concat` demuxer / `concat` filter without intermediate files where feasible).
2. **Assembly pass:** concat the teaser clip + body segments, overlay FX and title, mux the music, and encode once to the final codec.

This keeps each step inspectable (you can play any `temp/segments/NNN.mp4`) and isolates failures.

> Optimization note: intermediate files cost disk/time. An alternative single-pass `concat` **filter** graph (all `trim`/`setpts` chains concatenated in memory) is documented as a faster path once correctness is proven. Start with intermediate files for debuggability; switch later if needed.

## Files & responsibilities

### `render/ffmpeg_builder.py`
Pure-ish builders returning FFmpeg argument lists / filtergraph strings (no execution):
- `build_segment_args(segment, media, render) -> list[str]` - trim + setpts + scale/pad/setsar for one segment.
- `build_teaser_args(teaser_spec, render) -> list[str]` - tail extract + time-fit + mask (`vignette`/`gblur`).
- `build_fx_filter(fx_events, render) -> str` - zoom (`scale`/`zoompan` or `crop` with time-keyed expressions) + `rotate`, with a base over-scale (e.g., 1.02) so rotation never reveals borders; exponential decay per event.
- `build_title_filter(title_spec) -> str` OR `generate_ass(title_spec) -> Path` - drawtext filtergraph or burned ASS subtitle.
- `build_concat_and_encode_args(clips, audio_path, render, overlays) -> list[str]` - concat, apply FX/title overlays, map audio, final encode.

Returning argument lists makes these **unit-testable by asserting on the generated command** without running FFmpeg.

### `render/renderer.py`
- Orchestrates: extract segments -> assemble -> encode, all via `utils.ffmpeg.run_ffmpeg`.
- Manages `temp/segments/` lifecycle (honor `--keep-temp`).
- Verifies the output exists and `ffprobe`-matches the target spec (resolution, fps, codecs, duration ~= music).

## Encode settings (locked)

```
-c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p
-r 60 -s 1080x1920 -vsync cfr
-c:a aac -b:a 192k
-movflags +faststart
```

- Force CFR `60fps` to normalize any VFR source.
- `+faststart` for web/streaming-friendly MP4.
- Scale/pad strategy: `scale` to cover then `crop` to `1080x1920` (fill, no letterbox) - configurable to `pad` if desired.

## FFmpeg technique notes

- **Speed:** `setpts=PTS/${speed_factor}` for video; audio is the untouched music track applied once at assembly (not per segment).
- **Concat:** prefer the `concat` demuxer with a generated list file for same-codec intermediates, or the `concat` filter when chaining in-memory.
- **Zoom punch with decay:** time-keyed `crop`/`scale` using `if(between(t,...))` expressions or `zoompan`; magnitude from `FxEvent`, decay over `decay_frames/fps` seconds.
- **Rotation:** `rotate=a=...` with the same time-window expression; pre-scale to hide corners.
- **Title:** burn ASS via `ass=temp/title.ass` (handles multi-color + box) or `drawtext` fallback; restrict to `window_s`.

## Dependencies

- All upstream plan artifacts; `utils/ffmpeg.py`; `RenderConfig`.

## Testing

- **Builder unit tests:** assert generated arg lists contain expected `setpts`, `scale`, `crop`, `rotate`, encode flags for representative inputs (no FFmpeg execution).
- **Smoke render:** on a few-second fixture, run the full render and `ffprobe` the result: resolution `1080x1920`, `60fps`, `h264`/`aac`, duration ~= music.
- **Concat continuity:** assert no gaps (segment count and summed duration match the plan).

## Acceptance criteria

- Produces a playable `output/result.mp4` at the locked spec from the sample assets.
- Speed changes and FX visibly land on beats; teaser + title appear in the first ~2.5 s.
- Output duration matches the music within a frame.

## Risks & mitigations

- **Filtergraph complexity/escaping (Windows paths, special chars):** centralize escaping in the builder; use ASS files to avoid drawtext escaping pain.
- **Quality loss from intermediate re-encode:** use a high-quality/lossless intermediate (e.g., `-crf 12` or ffv1) for segments, final encode once at `crf 18`.
- **Slow renders:** start correct, then offer the single-pass `concat` filter path and `-preset` tuning.
- **A/V drift:** mux audio once at assembly against the fixed output clock; never speed-adjust the music.
