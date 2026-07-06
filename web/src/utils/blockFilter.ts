import type { MusicBlock } from "../types";

/** Client-side AND filter for target duration and slot count. `null` = Any. */
export function filterBlocks(
  blocks: MusicBlock[],
  targetDurationFilter: number | null,
  slotCountFilter: number | null,
): MusicBlock[] {
  return blocks.filter(
    (b) =>
      (targetDurationFilter === null ||
        b.preset_target_duration_s === targetDurationFilter) &&
      (slotCountFilter === null ||
        b.expected_slot_count === slotCountFilter),
  );
}
