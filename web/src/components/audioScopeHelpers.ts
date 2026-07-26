import type { MusicBlock, WaveformPayload } from "../types";

export const TARGET_ANY_CHIP_ID = "audio-scope-panel-target-any";
export const SLOT_ANY_CHIP_ID = "audio-scope-panel-slot-any";

/** Stable list identity — block ids repeat across catalog preset buckets. */
export function blockInstanceKey(block: MusicBlock): string {
  const preset = block.preset_target_duration_s ?? "active";
  return `${preset}:${block.id}:${block.start_s}:${block.end_s}`;
}

/** Whether this catalog row matches the active plan selection. */
export function isBlockInstanceSelected(
  block: MusicBlock,
  selectedBlockId: string | null,
  targetDurationS: number,
): boolean {
  if (!selectedBlockId || block.id !== selectedBlockId) {
    return false;
  }
  if (block.preset_target_duration_s == null) {
    return true;
  }
  return block.preset_target_duration_s === targetDurationS;
}

/** Block pool for client-side filters: catalog union or active-plan fallback. */
export function blockPoolFromWaveform(
  waveform: WaveformPayload,
  activeBlocks: MusicBlock[],
): MusicBlock[] {
  if (waveform.all_blocks && waveform.all_blocks.length > 0) {
    return waveform.all_blocks;
  }
  return activeBlocks;
}

/** Slot chip counts after optional target-duration filter. */
export function slotBlockCountsFromPool(
  pool: MusicBlock[],
  slotPresetValues: readonly number[],
): Map<number, number> {
  const counts = new Map<number, number>();
  for (const value of slotPresetValues) {
    counts.set(
      value,
      pool.filter((block) => block.expected_slot_count === value).length,
    );
  }
  return counts;
}

/** Duration presets that have at least one block in the pool. */
export function durationPresetsWithBlocks(
  pool: MusicBlock[],
  presetValues: readonly number[],
): Set<number> {
  const presets = new Set<number>();
  for (const value of presetValues) {
    if (pool.some((block) => block.preset_target_duration_s === value)) {
      presets.add(value);
    }
  }
  return presets;
}
