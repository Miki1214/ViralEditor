# Phase 2 - Audio DSP & Temporal Analysis (BeatViz Core)

**Goal:** Convert the music track into a precise `AudioTimeline` (global BPM + classified transients with normalized amplitudes) that drives speed-ramping and spatial FX.

**Status:** Core. Depends on [Phase 0](phase-0-scaffolding.md), [Phase 1](phase-1-config-ingestion.md).

---

## Objective

Implement the digital signal processing that extracts beat structure from the music: global BPM, onset/transient timestamps, normalized energy per transient, and a coarse classification into `percussive`, `bass`, and `drop`. Output is a pure, serializable `AudioTimeline`.

## Deliverables

- `audio/beat_detector.py` - pure function `analyze_audio(audio_path, *, config) -> AudioTimeline`.
- `temp/audio_timeline.json` matching the schema from the high-level plan.
- Optional cached onset envelope (`temp/onset_envelope.npy`) for Phase 3 reuse.

## Contract

### Output: `AudioTimeline`
```json
{
  "global_bpm": 128.0,
  "audio_duration_seconds": 32.41,
  "sample_rate": 22050,
  "transients": [
    {"timestamp_ms": 1180, "amplitude_normalized": 0.88, "type": "percussive"},
    {"timestamp_ms": 4720, "amplitude_normalized": 0.99, "type": "drop"}
  ]
}
```

## Detailed design

### Pipeline (all via `librosa`)
1. **Load:** `y, sr = librosa.load(audio_path, sr=22050, mono=True)`. Downmix to mono and a fixed sample rate for reproducibility and speed.
2. **Onset strength envelope:** `onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)`. This is the spectral-flux energy curve over time; also reused by Phase 3.
3. **Global BPM:** `tempo = librosa.feature.rhythm.tempo(onset_envelope=onset_env, sr=sr)` (autocorrelation over the onset envelope). Store as float.
4. **Transient (onset) detection:** `onsets = librosa.onset.onset_detect(onset_envelope=onset_env, sr=sr, hop_length=512, backtrack=True, units="time")`. Backtracking snaps onsets to the local energy minimum for tighter visual sync.
5. **Per-onset amplitude:** sample the onset envelope (or local RMS) at each onset; normalize to `[0,1]` against the track's max.
6. **Classification:**
   - `drop`: onsets whose normalized amplitude is in the top percentile (e.g., >= 0.92) AND separated by a minimum gap - these get slow-motion stabilization in Phase 3.
   - `bass`: onsets dominated by low-frequency energy (compare energy in a sub-200 Hz band via an STFT/mel split) - these trigger rotation shake in Phase 4.
   - `percussive`: everything else.
   - Use `librosa.effects.hpss` (harmonic-percussive separation) or a low-band energy ratio to distinguish bass vs general percussive hits.
7. **Assemble** `AudioTimeline`, convert onset times to `timestamp_ms` (rounded int), sort, dedupe near-duplicates within a small window.

### Configuration knobs (with defaults)
- `hop_length = 512`, `target_sr = 22050`.
- `drop_percentile = 0.92`, `min_drop_gap_ms = 1500`.
- `bass_band_hz = 200`, `bass_energy_ratio = 0.6`.
- `dedupe_window_ms = 60`.

### Purity & testability
`analyze_audio` takes a path, returns a model, writes nothing. The pipeline layer (Phase 7) is responsible for persisting `temp/audio_timeline.json`. This keeps the DSP unit-testable on synthetic signals.

## Dependencies

- `librosa`, `numpy`, `scipy`, `soundfile` from [Phase 0](phase-0-scaffolding.md).
- `audio_duration_seconds` should match the audio `MediaInfo` from [Phase 1](phase-1-config-ingestion.md) (sanity check; tolerate small decode differences).

## Testing

- **Synthetic click track:** generate a signal with impulses at known times (e.g., every 500 ms) and assert detected onsets land within tolerance.
- **Known-BPM loop:** feed a metronome at 120 BPM; assert `global_bpm` ~= 120 (allow half/double-tempo ambiguity, handle by clamping to a musical range).
- **Drop classification:** craft a quiet-then-loud transition; assert the loud hit classifies as `drop`.
- **Determinism:** same input -> identical timeline.

## Acceptance criteria

- Running on the sample music produces a plausible BPM and a non-empty, sorted transient list with at least one `drop`.
- `temp/audio_timeline.json` validates against the documented schema.
- Detection completes in seconds for a sub-minute track.

## Risks & mitigations

- **Octave/tempo errors (half or double BPM):** clamp detected tempo into a sane band (e.g., 60-180) by folding; log the raw value.
- **Over-detection on busy mixes:** dedupe window + amplitude threshold; expose knobs in config.
- **librosa/numba cold start latency:** acceptable for CLI; note it in logs.
