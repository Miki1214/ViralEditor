---
name: Default whole-clip speed-fit on upload
overview: When a clip is dropped/uploaded onto a storyboard slot, default the crop to the entire clip (0 to full duration) instead of trimming to the slot's target duration, so the backend's existing speed_factor = crop_duration / target_duration_s math naturally speeds up or slows down the whole clip to exactly fill the slot.
todos:
  - id: baseline
    content: Run baseline web + python tests to confirm clean state
    status: completed
  - id: red-test
    content: Add failing test for defaultAssignCropEndS in hookCrop.test.ts
    status: completed
  - id: green-impl
    content: Implement defaultAssignCropEndS in hookCrop.ts minimally to pass
    status: completed
  - id: wire-up
    content: Use defaultAssignCropEndS in StoryboardPanel.tsx assignFileToSlot
    status: completed
  - id: backend-regression
    content: Add/verify Python regression test in test_storyboard.py for whole-clip speed fit (speedup + slowdown cases)
    status: completed
  - id: refactor-verify
    content: Re-run full web + python test suites, confirm no regressions
    status: completed
isProject: false
---

## Root cause

Backend already supports arbitrary per-slot speed fitting. `storyboard_to_segments` in [src/viral_editor/audio/storyboard.py](src/viral_editor/audio/storyboard.py) (lines 1145-1185) computes:

```python
crop_duration = crop_end - crop_start
out_duration = max(slot.target_duration_s, 1e-6)
speed = crop_duration / out_duration
```

This is unbounded and already used by the ffmpeg filter chain (`setpts`) in [filter_builders.py](src/viral_editor/video/filter_builders.py). So if `crop_start_s=0` / `crop_end_s=<full clip duration>` is stored on the slot, the render already stretches/compresses the whole clip to fit `target_duration_s` — no backend change needed.

The only place that currently prevents this is the frontend default-assignment logic in `assignFileToSlot` in [web/src/components/StoryboardPanel.tsx](web/src/components/StoryboardPanel.tsx) (lines 223-254):

```ts
let endS = slot.target_duration_s;
try {
  const duration = await probeVideoDuration(objectUrl);
  if (duration != null) {
    endS = isHookFamilyRole(slot.role)
      ? duration
      : Math.min(duration, slot.target_duration_s);   // <-- trims clip-like/punch roles to slot length
  }
} finally { ... }
await onAssignClip(slot.id, file, 0, endS, transform);
```

Hook-family roles (`hook`, `hook_start`, `hook_end`) already default to full `duration` (matches desired behavior). Non-hook roles (`clip`, `punch`, `filler`) are clamped with `Math.min(duration, target_duration_s)`, which is exactly the "only part of video matching slot duration" bug.

## Confirmed scope (per user answers)

- Apply the whole-clip default to all clip-like roles, including `punch` (its extra `_PUNCH_SPEED` multiplier on the backend still applies on top, unchanged).
- No new speed clamp/guard — keep unbounded, matching existing backend behavior.
- Manual crop-trim UI (`ClipCropTimeline`, drag-to-crop) stays exactly as-is; this only changes the automatic default applied right after upload/drop.

## Change

1. Extract the default-crop-end calculation into a small pure, testable function in [web/src/utils/hookCrop.ts](web/src/utils/hookCrop.ts) (co-located with `isHookFamilyRole`, matching existing pattern for `hookUnifiedCrop`/`slotCropRange`):

```ts
/** Default crop-end applied right after a clip is uploaded/dropped onto a slot. */
export function defaultAssignCropEndS(_role: StorySlot["role"], clipDurationS: number): number {
  return clipDurationS;
}
```

(kept as a tiny named function, not inlined, purely so it's independently unit-testable and documents intent — role param kept for future flexibility/readability even though all roles now behave the same way).

2. Update `assignFileToSlot` in [StoryboardPanel.tsx](web/src/components/StoryboardPanel.tsx) to use it:

```ts
let endS = slot.target_duration_s;
try {
  const duration = await probeVideoDuration(objectUrl);
  if (duration != null) {
    endS = defaultAssignCropEndS(slot.role, duration);
  }
} finally { ... }
```

3. No backend changes required — verify with existing `storyboard_to_segments` tests in [tests/test_storyboard.py](tests/test_storyboard.py) that full-clip crop + short/long target duration already produces the expected `speed_factor` (add a regression case there if uncovered).

## TDD execution (per skill)

1. Baseline: run `web` tests (`cd web && npm test -- --run`) and relevant Python tests (`pytest tests/test_storyboard.py -v`) to confirm clean starting state.
2. Red: add a failing test in `web/src/utils/hookCrop.test.ts` asserting `defaultAssignCropEndS("clip", 12)` returns `12` (whole clip) rather than being capped to a shorter target duration — write the test first, run it, confirm it fails (function doesn't exist yet).
3. Green: implement `defaultAssignCropEndS` minimally, rerun, confirm pass.
4. Wire it into `assignFileToSlot`; add/extend a Python regression test in `tests/test_storyboard.py` confirming `storyboard_to_segments` yields `speed_factor = clip_duration / target_duration_s` when a slot's crop spans the full source clip (covering both a slowdown case, clip shorter than slot, and a speedup case, clip longer than slot).
5. Refactor: re-run full `npm test -- --run` and `pytest tests/test_storyboard.py -v` to check no regressions, then stop (no commit unless asked).

## Files touched

- [web/src/utils/hookCrop.ts](web/src/utils/hookCrop.ts) — add `defaultAssignCropEndS`
- [web/src/utils/hookCrop.test.ts](web/src/utils/hookCrop.test.ts) — new test
- [web/src/components/StoryboardPanel.tsx](web/src/components/StoryboardPanel.tsx) — use the helper in `assignFileToSlot`
- [tests/test_storyboard.py](tests/test_storyboard.py) — regression test for whole-clip speed fit (only if not already covered)
