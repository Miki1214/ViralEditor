---
name: Smoother audio loop crossfade
overview: Make the music loop-point crossfade smoother by lengthening it and switching from a linear fade curve to a true equal-power curve, in the shared loop-seam helper used by previews, proxy render, and final render.
todos:
  - id: red-curve-test
    content: "Red: update curve assertion in test_loop_seam.py to expect qsin, confirm it fails"
    status: completed
  - id: green-curve-audition
    content: "Green: switch build_loop_audition_filter curve to c1=qsin:c2=qsin"
    status: completed
  - id: red-seam-only-curve-test
    content: "Red: add qsin assertion for build_loop_seam_only_filter, confirm it fails"
    status: completed
  - id: green-seam-only-curve
    content: "Green: switch build_loop_seam_only_filter curve to c1=qsin:c2=qsin"
    status: completed
  - id: red-default-duration-test
    content: "Red: add test asserting DEFAULT_CROSSFADE_S == 0.12, confirm it fails"
    status: completed
  - id: green-default-duration
    content: "Green: bump DEFAULT_CROSSFADE_S to 0.12"
    status: completed
  - id: render-length-invariant-test
    content: Add/verify test proving total render duration (plan_output_duration_s / expected_duration_s) is unaffected by crossfade changes
    status: completed
  - id: refactor-docstrings
    content: "Refactor: fix docstrings/comments to accurately describe equal-power qsin curve"
    status: completed
  - id: full-verify
    content: Run full pytest suite for loop_seam, final_render, proxy_render and confirm all green
    status: completed
isProject: false
---

## Root cause

`src/viral_editor/audio/loop_seam.py` builds the ffmpeg `acrossfade` graphs used everywhere a music track is looped (audition preview, seam-only preview, proxy render, final render — all via `ensure_loop_seam_audio` in `src/viral_editor/audio/preview.py`):

```28:41:src/viral_editor/audio/loop_seam.py
def build_loop_audition_filter(
    start_s: float,
    duration_s: float,
    *,
    crossfade_s: float = DEFAULT_CROSSFADE_S,
) -> str:
    """FFmpeg filter graph: segment + equal-power crossfade loop audition."""
    crossfade_s = min(crossfade_s, duration_s / 4.0)
    return (
        f"[0:a]atrim=start={start_s:.6f}:duration={duration_s:.6f},"
        f"asetpts=PTS-STARTPTS,aresample=44100[seg];"
        f"[seg]asplit=2[a][b];"
        f"[a][b]acrossfade=d={crossfade_s:.4f}:c1=tri:c2=tri[out]"
    )
```

Two issues cause the "sharp" crossfade:

1. `DEFAULT_CROSSFADE_S = 0.04` (40ms) is very short.
2. `c1=tri:c2=tri` is a **linear** fade curve, not equal-power (despite the docstring/comment claiming "equal-power"). A linear crossfade produces an audible loudness dip in the middle of the fade, which is perceived as a "click"/seam.

The same curve is duplicated in `build_loop_seam_only_filter`.

## Changes

1. `src/viral_editor/audio/loop_seam.py`
   - Bump `DEFAULT_CROSSFADE_S` from `0.04` to `0.12` (120ms).
   - Change the crossfade curve in both `build_loop_audition_filter` and `build_loop_seam_only_filter` from `c1=tri:c2=tri` to `c1=qsin:c2=qsin` (quarter-sine, true equal-power/constant-power curve) so the docstrings ("equal-power crossfade") actually match the behavior.
   - No signature/behavior changes beyond the constant and curve string — `crossfade_s` remains clamped against `duration_s / 4.0`, so short segments are still safe.

2. `tests/test_loop_seam.py`
   - Update `test_build_loop_audition_filter_uses_equal_power_crossfade` to assert `"c1=qsin:c2=qsin" in graph` instead of `"c1=tri:c2=tri"`.
   - Add/keep an assertion covering `build_loop_seam_only_filter` using the new curve too.

3. No changes needed to `final_render.py` / `proxy_render.py` / `preview.py` — they all just call `ensure_loop_seam_audio`, which delegates to the updated default, so the smoother loop automatically applies to previews and actual renders alike.

## Why render length is safe

`final_render.py` computes total output length independently of the music-loop internals:

```249:299:src/viral_editor/video/final_render.py
total_duration_s = plan_output_duration_s(plan, transitions=transitions)
...
    loop_wav = ensure_loop_seam_audio(... music_start_s, music_end_s ...)
    command.extend(["-stream_loop", "-1", "-i", str(loop_wav)])
...
        expected_duration_s=total_duration_s,
```

`total_duration_s` (`plan_output_duration_s`) never depends on `DEFAULT_CROSSFADE_S`. The looped music input is fed with `-stream_loop -1` and the encode is cut/muxed to `total_duration_s` via `-t`, then `_validate_render_output`-style ffprobe check (around line 79) raises `ValueError` if `probed_duration` drifts from `expected_duration_s` beyond tolerance. So lengthening/reshaping the crossfade inside the looped music segment cannot change the final render's video/audio duration — it can only change where inside the loop cycle the smoothing happens. This existing check is our regression guard; we will also add an explicit unit test for it (see TDD plan below) rather than relying on it implicitly.

## TDD execution (per `/tdd` protocol)

Follow strict Red→Green→Refactor, one test at a time, running `pytest` after every step (venv must be activated first: `& c:/Sources/ViralAutomation/.venv/Scripts/Activate.ps1`).

1. **Red 1 — curve assertion**: edit `tests/test_loop_seam.py::test_build_loop_audition_filter_uses_equal_power_crossfade` to assert `"c1=qsin:c2=qsin" in graph`. Run it, confirm it fails against current `tri` implementation.
   **Green 1**: change `build_loop_audition_filter`'s curve to `c1=qsin:c2=qsin`. Run test, confirm pass.

2. **Red 2 — seam-only curve assertion**: add a new assertion in `test_build_loop_seam_only_filter_wraps_tail_to_head` (or a new test) asserting `"c1=qsin:c2=qsin" in graph` for `build_loop_seam_only_filter`. Confirm it fails.
   **Green 2**: change `build_loop_seam_only_filter`'s curve to match. Confirm pass.

3. **Red 3 — default duration**: add a small test (e.g. `test_default_crossfade_is_120ms`) asserting `DEFAULT_CROSSFADE_S == 0.12`. Confirm it fails against current `0.04`.
   **Green 3**: bump `DEFAULT_CROSSFADE_S` to `0.12`. Confirm pass.

4. **Red 4 — render-length invariant (new safety test)**: add a test in `tests/test_final_render.py` that renders/build-args with the new crossfade default and asserts `plan_output_duration_s(plan, transitions=transitions)` (or the resulting `expected_duration_s` passed to the ffprobe validation call) is bit-for-bit identical to the value computed before this change (i.e. independent of `DEFAULT_CROSSFADE_S`/`crossfade_s`). This should already pass (it's a characterization test proving the invariant holds), but per strict TDD we still write it before/alongside the refactor and watch it go green — if it ever fails, that's a real regression to stop and fix, not to loosen.

5. **Refactor**: re-read `loop_seam.py` for clarity, ensure docstrings ("equal-power crossfade") now correctly describe the `qsin` curve, remove any now-redundant comments.

## Verification

- Run `pytest tests/test_loop_seam.py tests/test_final_render.py tests/test_proxy_render.py -v` — all green, including the new render-length invariant test.
- Confirm no other test in the suite hardcodes `0.04` or `c1=tri` for these filters (`rg "0\.04|c1=tri" tests/`).
- Optionally regenerate a preview for an existing job (e.g. `temp/jobs/.../temp/previews/`) to listen to the new loop seam.