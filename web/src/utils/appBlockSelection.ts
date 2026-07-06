import type { MusicBlock } from "../types";

/** Storyboard target to apply when user selects a block from another preset bucket. */
export function targetDurationForBlockSelection(
  block: MusicBlock,
  currentTargetDurationS: number,
): number | null {
  if (
    block.preset_target_duration_s != null &&
    block.preset_target_duration_s !== currentTargetDurationS
  ) {
    return block.preset_target_duration_s;
  }
  return null;
}
