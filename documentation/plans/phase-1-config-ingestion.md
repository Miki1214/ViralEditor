# Phase 1 - Configuration & Ingestion

**Goal:** Turn a JSON job file plus media paths into validated, typed configuration and probed `MediaInfo`, establishing the single source of truth the rest of the pipeline consumes.

**Status:** Core. Depends on [Phase 0](phase-0-scaffolding.md).

---

## Objective

Parse and validate the job request (paths, hook text, style, render settings), verify the media exists and is readable, and probe both streams with `ffprobe`. Define the output timeline rule: **the music track duration determines the final video length**; the timelapse footage is later time-remapped to fill it.

## Deliverables

- `config.py`: `JobConfig`, `StyleConfig`, `TitleConfig`, `RenderConfig` (pydantic).
- `ingest/loader.py`: validation + `ffprobe` probing -> `MediaInfo`.
- `config/job.example.json`: fully documented example.

## Contracts

### Input
A JSON job file:

```json
{
  "video_path": "assets/timelapse.mp4",
  "audio_path": "assets/track.mp3",
  "output_path": "output/result.mp4",
  "seed": 42,
  "hook": {
    "text": "I built this in 30 days",
    "emphasis_words": ["30", "days"]
  },
  "style": {
    "font_family": "Montserrat Black",
    "fill_color": "#FFFFFF",
    "emphasis_color": "#FFD700",
    "box_color": "rgba(0,0,0,0.85)",
    "safe_padding_pct": 10
  },
  "render": {
    "width": 1080,
    "height": 1920,
    "fps": 60,
    "vcodec": "libx264",
    "acodec": "aac",
    "crf": 18,
    "preset": "medium",
    "pix_fmt": "yuv420p"
  },
  "speed_ramp": { "s_min": 1.0, "s_max": 30.0, "alpha": 0.0 },
  "teaser": { "tail_fraction": 0.05, "duration_s": 2.5, "mask": "vignette" }
}
```

> `render`, `speed_ramp`, and `teaser` blocks are optional with sane defaults baked into the pydantic models so a minimal job file only needs the three paths and a hook.

### Output
- A validated `JobConfig` object.
- `MediaInfo` for video and for audio, serialized to `temp/media_info.json`.

## Files & responsibilities

### `config.py`
- `RenderConfig` with the locked defaults: `1080x1920`, `60`, `libx264`, `aac`, `crf=18`, `preset="medium"`, `pix_fmt="yuv420p"`.
- `StyleConfig` and `TitleConfig` (hook text, emphasis words, colors, font, safe padding).
- `SpeedRampConfig` (`s_min`, `s_max`, `alpha`) and `TeaserConfig` (`tail_fraction`, `duration_s`, `mask`).
- `JobConfig` ties them together with `extra="forbid"` (typos in the job file fail loudly).
- A `JobConfig.load(path)` classmethod that reads JSON and validates, raising a readable aggregated error on invalid input.
- Path fields validated as `pathlib.Path`; relative paths resolved against the job file's directory or CWD (decide once, document it - default: relative to CWD).

### `ingest/loader.py`
- `probe_media(path) -> MediaInfo` using `utils.ffmpeg.run_ffprobe_json` with `-show_streams -show_format`. Extract:
  - video: `duration`, `r_frame_rate` -> fps (parse the `num/den`), `width`, `height`, `codec_name`.
  - audio: `duration`, `sample_rate`, `channels`, `codec_name`, presence.
- `validate_job(cfg) -> IngestResult`: confirms files exist and are non-empty, the video has a video stream, the audio file decodes, output directory is writable; warns if the source video is much shorter than the music (it will need looping in Phase 3).
- Returns `MediaInfo` for both streams.

## Detailed design notes

- **Single timeline authority:** record `output_duration_s = audio MediaInfo.duration`. Every downstream planner uses this number so segments, FX, teaser, and title windows all share one clock.
- **fps parsing:** `r_frame_rate` comes as a fraction (e.g., `"30000/1001"`); compute as float and keep both raw and rounded.
- **Graceful errors:** wrap `ffprobe` failures into a domain `IngestError` with the offending path.

## Dependencies

- [Phase 0](phase-0-scaffolding.md) for `utils/ffmpeg.py` and `models.py`.

## Testing

- `tests/test_config.py`: valid minimal job loads with defaults applied; unknown key rejected; bad color/enum rejected.
- `tests/test_ingest.py`: probe a tiny fixture clip (or mock `ffprobe` JSON) and assert parsed `MediaInfo`; assert friendly error for missing file.
- Path resolution test (relative vs absolute).

## Acceptance criteria

- A minimal 3-path job file loads and validates.
- `MediaInfo` for the sample assets is produced and written to `temp/media_info.json`.
- `output_duration_s` is derived from the audio track.

## Risks & mitigations

- **Variable frame rate (VFR) sources:** detect and log; Phase 6 will normalize to CFR `60fps` during encode.
- **Exotic container/codec:** `ffprobe` still reports; if decode fails, surface a clear remux suggestion.
