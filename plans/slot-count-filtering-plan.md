# Slot Count Filtering for Music Blocks

## Problem Analysis

```
[Current Flow]                    [Target Flow]
═══════════════                   ═══════════════

User selects duration ──→ Filter blocks  User selects duration ──→┐
(chips: 5s, 10s, 15s...)    ──→  OR  User selects slot count ────┤ AND filter blocks
                                              │
                              Slot chips: 1..10 ──────────────────┘
                                              │
                                         Matching blocks shown
```

## Architecture Overview

```
App.tsx (state owner)
  ├── selectedDurationS (existing)
  ├── selectedSlotCount (NEW)
  │
  ▼
AudioScopePanel.tsx (UI: duration chips + slot chips)
  ├── TARGET_DURATION_PRESETS (existing: 5s, 10s...)
  ├── SLOT_COUNT_PRESETS      (NEW: 1..10 slots)
  └── filter blocks by BOTH criteria
  │
  ▼
WaveformPayload.blocks (MusicBlock[])
  └── needs expected_slot_count field from backend
```

## Data Flow

```
Backend (Python)                    Frontend (React)
═══════════════════════             ═══════════════════════

storyboard.py:                      types.ts:
_recommended_slot_count()           MusicBlock {
    → computes N slots per block       expected_slot_count?: int  ← NEW
                                      WaveformPayload {
update_music_selection()               blocks: MusicBlock[]
    returns blocks with                slot_count_filter?: int    ← NEW
    expected_slot_count field          }
                                      │
App.tsx:                            AudioScopePanel.tsx:
selectedSlotCount state              SLOT_COUNT_PRESETS = [1..10]
passed as prop                       onSlotCountChange handler
                                      │
                                      filterBlocks()
                                        → duration matches AND
                                        → slot_count == selectedSlotCount
```

## Slot Count Presets

Based on the existing `_recommended_slot_count` logic in [`src/viral_editor/audio/storyboard.py:38`](src/viral_editor/audio/storyboard.py:38):
- Minimum slot width is `_MIN_SLOT_S` (need to check exact value)
- Max is `_MAX_SLOT_COUNT` (need to check exact value)
- Ideal formula: `int(round(duration / 4.0))`

For the UI, presets will be `[1, 2, 3, 4, 5, 6, 7, 8, 9, 10]`.

## TDD Phases

### Phase 1: Write failing test for filterBlocksBySlotCount utility (Red)

Create `web/src/utils/slotCountFilter.test.ts` with tests:

- **test: includes blocks matching selected slot count**
  - Given blocks with expected_slot_count [3, 5, 8] and selectedSlotCount=5
  - When filterBlocksBySlotCount(blocks, 5)
  - Then returns only the block with expected_slot_count === 5

- **test: excludes blocks not matching selected slot count**
  - Given blocks with expected_slot_count [3, 5, 8] and selectedSlotCount=5
  - When filterBlocksBySlotCount(blocks, 5)
  - Then returns only blocks where expected_slot_count === 5

- **test: when no slot filter (null), all blocks pass through**
  - Given blocks with expected_slot_count [3, 5, 8] and selectedSlotCount=null
  - When filterBlocksBySlotCount(blocks, null)
  - Then returns all blocks unchanged

- **test: handles empty block list**
  - Given empty blocks array and selectedSlotCount=5
  - When filterBlocksBySlotCount([], 5)
  - Then returns empty array

### Phase 2: Implement filterBlocksBySlotCount utility (Green)

Create `web/src/utils/slotCountFilter.ts`:

```ts
export function filterBlocksBySlotCount(
  blocks: Array<{ expected_slot_count?: number | null }>,
  selectedSlotCount: number | null,
): typeof blocks {
  if (selectedSlotCount == null) {
    return blocks;
  }
  return blocks.filter((block) => block.expected_slot_count === selectedSlotCount);
}
```

### Phase 3: Add expected_slot_count to MusicBlock type in types.ts

In [`web/src/types.ts:55`](web/src/types.ts:55), add to `MusicBlock` interface:

```ts
export interface MusicBlock {
  // ... existing fields ...
  expected_slot_count?: number | null;  // NEW
}
```

### Phase 4: Add SLOT_COUNT_PRESETS constant [1..10] to durations.ts

In [`web/src/constants/durations.ts`](web/src/constants/durations.ts), add:

```ts
export const SLOT_COUNT_PRESETS = Array.from({ length: 10 }, (_, i) => ({
  label: `${i + 1} slot${i + 1 > 1 ? "s" : ""}`,
  value: i + 1,
})) as const;
```

### Phase 5: Add slot count chips UI row in AudioScopePanel

In [`web/src/components/AudioScopePanel.tsx`](web/src/components/AudioScopePanel.tsx):

- Import `SLOT_COUNT_PRESETS` from durations
- Add new prop `selectedSlotCount: number | null` and `onSlotCountChange: (count: number | null) => void`
- Add a new chip row below the existing duration chips
- Each chip shows "N slot(s)" with active/unavailable states
- Unavailable when track is too short for N slots (based on `_MIN_SLOT_S`)

### Phase 6: Thread selectedSlotCount state through App.tsx → AudioScopePanel

In [`web/src/App.tsx`](web/src/App.tsx):

- Add state: `const [selectedSlotCount, setSelectedSlotCount] = useState<number | null>(null);`
- Pass to `AudioScopePanel`: `selectedSlotCount={selectedSlotCount}` and `onSlotCountChange={setSelectedSlotCount}`

### Phase 7: Apply combined duration + slot count filter to blocks list

In `AudioScopePanel`, compute filtered blocks using `useMemo`:

```ts
const filteredBlocks = useMemo(() => {
  let result = blocks;
  if (selectedSlotCount != null) {
    result = filterBlocksBySlotCount(result, selectedSlotCount);
  }
  return result;
}, [blocks, selectedSlotCount]);
```

Replace `blocks` with `filteredBlocks` in the block list rendering.

### Phase 8: Display expected slot count badge on MusicBlockCard

In [`web/src/components/MusicBlockCard.tsx`](web/src/components/MusicBlockCard.tsx):

- Add `expected_slot_count?: number | null` to `MusicBlock` type (already done in Phase 3)
- Pass `block.expected_slot_count` through the existing block prop
- Display as a small badge: "N slots" next to loop quality info

### Phase 9: Run full test suite (no regressions)

Run `npm test` in the `web/` directory and verify all existing tests pass.

## File Changes Summary

| File | Change |
|------|--------|
| `web/src/utils/slotCountFilter.ts` | **NEW** — pure filter function |
| `web/src/utils/slotCountFilter.test.ts` | **NEW** — TDD tests |
| `web/src/types.ts:55` | Add `expected_slot_count?` to MusicBlock |
| `web/src/constants/durations.ts` | Add `SLOT_COUNT_PRESETS` [1..10] |
| `web/src/components/AudioScopePanel.tsx` | Slot chips UI + filter logic |
| `web/src/App.tsx` | Thread state through |
| `web/src/components/MusicBlockCard.tsx` | Display slot count badge |

## Backend Notes

The backend should return `expected_slot_count` per block in the waveform response. If not already present, add it using `_recommended_slot_count()` from [`src/viral_editor/audio/storyboard.py:38`](src/viral_editor/audio/storyboard.py:38).

Frontend behavior when field is missing: blocks without `expected_slot_count` will not match any slot filter (by design — the backend must provide this data for filtering to work).
