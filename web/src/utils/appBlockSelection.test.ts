import { describe, expect, it } from "vitest";
import { targetDurationForBlockSelection } from "./appBlockSelection";
import type { MusicBlock } from "../types";

function makeBlock(overrides: Partial<MusicBlock> = {}): MusicBlock {
  return {
    id: "blk-1",
    start_s: 0,
    end_s: 10,
    duration_s: 10,
    score: 0.8,
    drop_count: 1,
    transient_count: 1,
    label: "test",
    reason: "test",
    loop_quality: 0.8,
    phrase_bars: 4,
    section_label: null,
    key: null,
    is_repeated_section: false,
    preset_target_duration_s: 15,
    expected_slot_count: 4,
    ...overrides,
  };
}

describe("targetDurationForBlockSelection", () => {
  it("returns null when block preset matches current storyboard target", () => {
    const block = makeBlock({ preset_target_duration_s: 10 });
    expect(targetDurationForBlockSelection(block, 10)).toBeNull();
  });

  it("returns preset when block belongs to a different target duration", () => {
    const block = makeBlock({ preset_target_duration_s: 15 });
    expect(targetDurationForBlockSelection(block, 10)).toBe(15);
  });

  it("returns null when block has no preset target tag", () => {
    const block = makeBlock({ preset_target_duration_s: undefined });
    expect(targetDurationForBlockSelection(block, 10)).toBeNull();
  });
});
