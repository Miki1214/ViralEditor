import type { StoryboardPayload, StorySlot } from "../types";
import {
  defaultAssignCropEndS,
  hookSourceBudgetS,
  hookUnifiedCrop,
  hookUnifiedLabelSpeed,
  isHookFamilyRole,
  slotCropRange,
} from "./hookCrop";

function hookSplitStoryboard(
  clipLen: number,
  payoffOut: number,
  buildOut: number,
  payoffSrcStart: number,
  payoffSrcEnd: number,
  buildSrcStart: number,
  buildSrcEnd: number,
): StoryboardPayload {
  const hookStart: StorySlot = {
    id: "slot_0_hook_start",
    order: 0,
    label: "Hook · start",
    role: "hook_start",
    out_start_s: 0,
    out_end_s: payoffOut,
    target_duration_s: payoffOut,
    transition_in: "cut",
    assigned_clip_id: "clip_a",
    crop_start_s: payoffSrcStart,
    crop_end_s: payoffSrcEnd,
    clip_filename: "clip.mp4",
    clip_source_url: null,
    rotation_deg: 0,
    fit_mode: "contain",
    spatial_crop: null,
  };
  const hookEnd: StorySlot = {
    id: "slot_0_hook_end",
    order: 1,
    label: "Hook · end",
    role: "hook_end",
    out_start_s: payoffOut,
    out_end_s: payoffOut + buildOut,
    target_duration_s: buildOut,
    transition_in: "cut",
    assigned_clip_id: "clip_a",
    crop_start_s: buildSrcStart,
    crop_end_s: buildSrcEnd,
    clip_filename: "clip.mp4",
    clip_source_url: null,
    rotation_deg: 0,
    fit_mode: "contain",
    spatial_crop: null,
  };
  return {
    music_block_id: "block_a",
    music_start_s: 0,
    music_end_s: 16,
    total_duration_s: 16,
    loop_to_hook: true,
    preview_ready: true,
    teaser: {
      enabled: true,
      tail_fraction: 0.5,
      duration_s: payoffOut,
      mask: "vignette",
    },
    spatial_fx: {
      enabled: false,
      intensity: 1,
      max_events_per_second: 4,
      translate_enabled: true,
      pan_beat_mode: "auto",
      pan_min_decay_s: 0.2,
      pan_energy_threshold: 0.45,
      pan_energy_floor: 0.2,
      pan_hook_enabled: true,
      pan_hook_by_s: 1.0,
    },
    retention: {
      interrupt_min_gap_s: 2,
      interrupt_max_gap_s: 5,
      hook_window_s: 4,
      early_hook_fx_by_s: 2,
      peak_snap_tolerance_s: 0.1,
    },
    slots: [hookStart, hookEnd],
  };
}

describe("isHookFamilyRole", () => {
  it("identifies hook roles", () => {
    expect(isHookFamilyRole("hook")).toBe(true);
    expect(isHookFamilyRole("hook_start")).toBe(true);
    expect(isHookFamilyRole("clip")).toBe(false);
  });
});

describe("hookUnifiedCrop", () => {
  it("merges hook_start and hook_end into contiguous span", () => {
    const storyboard = hookSplitStoryboard(10, 2, 2, 5, 10, 0, 5);
    const slot = storyboard.slots[0];
    expect(hookUnifiedCrop(storyboard, slot)).toEqual({ startS: 0, endS: 10 });
  });
});

describe("hookSourceBudgetS", () => {
  it("sums hook_start and hook_end output targets", () => {
    const storyboard = hookSplitStoryboard(10, 2, 2, 5, 10, 0, 5);
    expect(hookSourceBudgetS(storyboard, storyboard.slots[0])).toBe(4);
  });
});

describe("slotCropRange", () => {
  it("uses hook unified span for hook family slots", () => {
    const storyboard = hookSplitStoryboard(10, 2, 2, 5, 10, 0, 5);
    expect(slotCropRange(storyboard, storyboard.slots[0])).toEqual({ startS: 0, endS: 10 });
  });

  it("uses the clip slot's own crop, not the hook unified span", () => {
    const storyboard = hookSplitStoryboard(14.48, 2, 2, 7.24, 14.48, 0, 7.24);
    const clipSlot: StorySlot = {
      id: "slot_1",
      order: 1,
      label: "Clip 1",
      role: "clip",
      out_start_s: 4,
      out_end_s: 8,
      target_duration_s: 3.99,
      transition_in: "xfade",
      assigned_clip_id: "clip_b",
      crop_start_s: 0,
      crop_end_s: 3.99,
      clip_filename: "MVI.mp4",
      clip_source_url: null,
      rotation_deg: 0,
      fit_mode: "contain",
      spatial_crop: null,
    };
    storyboard.slots.splice(1, 0, clipSlot);
    const hookUnified = hookUnifiedCrop(storyboard, storyboard.slots[0]);
    expect(hookUnified.endS - hookUnified.startS).toBeCloseTo(14.48, 2);
    expect(slotCropRange(storyboard, clipSlot)).toEqual({ startS: 0, endS: 3.99 });
    expect(slotCropRange(storyboard, clipSlot).endS).not.toBeCloseTo(hookUnified.endS, 1);
  });
});

describe("defaultAssignCropEndS", () => {
  it("uses the full clip duration for clip slots instead of capping to target duration", () => {
    expect(defaultAssignCropEndS("clip", 12)).toBe(12);
  });

  it("uses the full clip duration for punch slots", () => {
    expect(defaultAssignCropEndS("punch", 8.5)).toBe(8.5);
  });

  it("uses the full clip duration for hook family slots", () => {
    expect(defaultAssignCropEndS("hook", 14.48)).toBe(14.48);
    expect(defaultAssignCropEndS("hook_start", 14.48)).toBe(14.48);
    expect(defaultAssignCropEndS("hook_end", 14.48)).toBe(14.48);
  });
});

describe("hookUnifiedLabelSpeed", () => {
  it("matches backend (U1-U0)/B formula", () => {
    const storyboard = hookSplitStoryboard(10, 2, 2, 5, 10, 0, 5);
    const slot = storyboard.slots[0];
    expect(hookUnifiedLabelSpeed(storyboard, slot)).toBeCloseTo(10 / 4, 4);
  });

  it("returns null for non-hook slots", () => {
    const storyboard = hookSplitStoryboard(10, 2, 2, 5, 10, 0, 5);
    const clipSlot: StorySlot = {
      ...storyboard.slots[0],
      id: "clip_1",
      role: "clip",
      crop_start_s: 0,
      crop_end_s: 4,
      target_duration_s: 4,
    };
    expect(hookUnifiedLabelSpeed(storyboard, clipSlot)).toBeNull();
  });
});
