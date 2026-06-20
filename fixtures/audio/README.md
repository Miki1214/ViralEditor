# Audio validation fixtures

Synthetic WAV files with documented hit times for checking onset detection, drop/bass classification, and Spatial FX placement.

## Files

| File | Purpose |
|------|---------|
| `validation_clicks.wav` | Clicks every **0.5 s** starting at **0.5 s** — onset timing |
| `validation_drop.wav` | Quiet ticks + loud hit at **2.5 s** — **drop** → zoom |
| `validation_bass.wav` | Low-frequency thumps at **0.75 / 1.75 / 2.75 s** — **bass** → rotate |
| `validation_mixed.wav` | Bass at **2.25 s**, drop at **3.75 s** — combined Spatial FX check |
| `manifest.json` | Ground-truth times, tolerances, and classifier output snapshot |

## Use in the app

1. Start the API and upload one of these files as music.
2. Open **Audio scope** — gold ticks = drops, blue = bass (full track).
3. Open **Storyboard scope** with Spatial FX enabled — gold = zoom, blue = rotate (after merge/cap).
4. Compare marker positions to `manifest.json` → `expected_transients`.

Allow roughly **80–150 ms** slop; librosa onset detection is not sample-exact.

## Regenerate

```bash
uv run python scripts/generate_audio_fixtures.py
```

This rewrites the WAV files and refreshes `verified_transients` in `manifest.json`.

## Automated check

```bash
uv run pytest tests/test_audio_fixtures.py -q
```
