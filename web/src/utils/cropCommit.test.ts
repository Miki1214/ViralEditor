import type { StorySlot } from "../types";
import { shouldCommitCrop } from "./cropCommit";
import { slotCropRange } from "./hookCrop";
import type { StoryboardPayload } from "../types";

function baseStoryboard(slots: StorySlot[]): StoryboardPayload {
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
      duration_s: 2,
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
    slots,
  };
}

describe("shouldCommitCrop", () => {
  const hookStart: StorySlot = {
    id: "slot_0_hook_start",
    order: 0,
    label: "Hook · start",
    role: "hook_start",
    out_start_s: 0,
    out_end_s: 2,
    target_duration_s: 2,
    transition_in: "cut",
    assigned_clip_id: "clip_a",
    crop_start_s: 10.06,
    crop_end_s: 20.12,
    clip_filename: "hook.mp4",
    clip_source_url: null,
    rotation_deg: 0,
    fit_mode: "contain",
    spatial_crop: null,
  };
  const hookEnd: StorySlot = {
    id: "slot_0_hook_end",
    order: 2,
    label: "Hook · end",
    role: "hook_end",
    out_start_s: 2,
    out_end_s: 4,
    target_duration_s: 2,
    transition_in: "cut",
    assigned_clip_id: "clip_a",
    crop_start_s: 0,
    crop_end_s: 10.06,
    clip_filename: "hook.mp4",
    clip_source_url: null,
    rotation_deg: 0,
    fit_mode: "contain",
    spatial_crop: null,
  };
  const storyboard = baseStoryboard([hookStart, hookEnd]);

  it("returns false when crop matches persisted unified span", () => {
    const current = slotCropRange(storyboard, hookStart);
    expect(shouldCommitCrop(storyboard, hookStart, current.startS, current.endS, false)).toBe(
      false,
    );
  });

  it("returns true when user shortens the unified hook crop", () => {
    expect(shouldCommitCrop(storyboard, hookStart, 0, 15, false)).toBe(true);
  });

  it("returns false while saving", () => {
    expect(shouldCommitCrop(storyboard, hookStart, 0, 15, true)).toBe(false);
  });
});
