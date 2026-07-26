import type { StoryboardPayload, StorySlot } from "../types";

export function isHookFamilyRole(role: StorySlot["role"]): boolean {
  return role === "hook" || role === "hook_start" || role === "hook_end";
}

/** Default crop-end applied right after a clip is uploaded/dropped onto a slot. */
export function defaultAssignCropEndS(_role: StorySlot["role"], clipDurationS: number): number {
  return clipDurationS;
}

/** Hook output budget (seconds) — sum of hook_start + hook_end targets, or single hook slot. */
export function hookSourceBudgetS(storyboard: StoryboardPayload, slot: StorySlot): number {
  if (slot.role === "hook") {
    return slot.target_duration_s;
  }
  if (slot.role === "hook_start" || slot.role === "hook_end") {
    const hookStart = storyboard.slots.find((entry) => entry.role === "hook_start");
    const hookEnd = storyboard.slots.find((entry) => entry.role === "hook_end");
    return (hookStart?.target_duration_s ?? 0) + (hookEnd?.target_duration_s ?? 0);
  }
  return slot.target_duration_s;
}

/** Per-slot source crop for the crop timeline (hook family uses unified span). */
export function slotCropRange(
  storyboard: StoryboardPayload,
  slot: StorySlot,
): { startS: number; endS: number } {
  if (isHookFamilyRole(slot.role)) {
    return hookUnifiedCrop(storyboard, slot);
  }
  return {
    startS: slot.crop_start_s ?? 0,
    endS: slot.crop_end_s ?? slot.target_duration_s,
  };
}

/** Contiguous source crop spanning hook / hook_start + hook_end (hook family only). */
export function hookUnifiedCrop(
  storyboard: StoryboardPayload,
  slot: StorySlot,
): { startS: number; endS: number } {
  if (slot.role === "hook") {
    return {
      startS: slot.crop_start_s ?? 0,
      endS: slot.crop_end_s ?? slot.target_duration_s,
    };
  }
  if (slot.role !== "hook_start" && slot.role !== "hook_end") {
    return slotCropRange(storyboard, slot);
  }
  const hookStart = storyboard.slots.find((entry) => entry.role === "hook_start");
  const hookEnd = storyboard.slots.find((entry) => entry.role === "hook_end");
  if (!hookStart || !hookEnd) {
    return {
      startS: slot.crop_start_s ?? 0,
      endS: slot.crop_end_s ?? slot.target_duration_s,
    };
  }
  const starts = [hookStart.crop_start_s, hookEnd.crop_start_s].filter(
    (value): value is number => value != null,
  );
  const ends = [hookStart.crop_end_s, hookEnd.crop_end_s].filter(
    (value): value is number => value != null,
  );
  return {
    startS: starts.length ? Math.min(...starts) : 0,
    endS: ends.length ? Math.max(...ends) : slot.target_duration_s,
  };
}

/** UI label speed for hook family: unified source span / hook output budget. */
export function hookUnifiedLabelSpeed(storyboard: StoryboardPayload, slot: StorySlot): number | null {
  if (!isHookFamilyRole(slot.role)) {
    return null;
  }
  const budget = hookSourceBudgetS(storyboard, slot);
  if (budget <= 0) {
    return null;
  }
  const crop = hookUnifiedCrop(storyboard, slot);
  const span = Math.max(crop.endS - crop.startS, 0);
  if (span <= 0) {
    return null;
  }
  return span / budget;
}

export function hookFamilyClipSlot(storyboard: StoryboardPayload, slot: StorySlot): StorySlot {
  if (slot.assigned_clip_id && slot.clip_source_url) {
    return slot;
  }
  if (!isHookFamilyRole(slot.role)) {
    return slot;
  }
  return (
    storyboard.slots.find(
      (entry) =>
        isHookFamilyRole(entry.role) && entry.assigned_clip_id && entry.clip_source_url,
    ) ?? slot
  );
}
