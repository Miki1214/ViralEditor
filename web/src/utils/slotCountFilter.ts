import type { MusicBlock } from "../types";

export function filterBlocksBySlotCount(
  blocks: MusicBlock[],
  selectedSlotCount: number | null,
): MusicBlock[] {
  if (selectedSlotCount == null) {
    return blocks;
  }
  return blocks.filter((block) => block.expected_slot_count === selectedSlotCount);
}
