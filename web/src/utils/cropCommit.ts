import { slotCropRange } from "./hookCrop";
import type { StoryboardPayload, StorySlot } from "../types";

/** Mirrors StoryboardPanel.commitCrop guard — exported for tests. */
export function shouldCommitCrop(
  storyboard: StoryboardPayload,
  slot: StorySlot,
  startS: number,
  endS: number,
  saving: boolean,
): boolean {
  if (saving) return false;
  const current = slotCropRange(storyboard, slot);
  const unchanged =
    Math.abs(current.startS - startS) < 0.001 && Math.abs(current.endS - endS) < 0.001;
  return !unchanged;
}
