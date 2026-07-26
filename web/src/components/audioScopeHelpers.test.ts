import { describe, expect, it } from "vitest";
import { blockInstanceKey } from "./audioScopeHelpers";
import type { MusicBlock } from "../types";

function makeBlock(overrides: Partial<MusicBlock> = {}): MusicBlock {
  return {
    id: "block_e",
    start_s: 0,
    end_s: 10,
    duration_s: 10,
    score: 0.9,
    drop_count: 1,
    transient_count: 1,
    label: "E",
    reason: "test",
    loop_quality: 0.8,
    phrase_bars: 4,
    section_label: null,
    key: "C",
    is_repeated_section: false,
    ...overrides,
  };
}

describe("blockInstanceKey", () => {
  it("differs for same block id across preset target buckets", () => {
    const block15 = makeBlock({ preset_target_duration_s: 15, start_s: 5, end_s: 20 });
    const block20 = makeBlock({ preset_target_duration_s: 20, start_s: 8, end_s: 28 });
    expect(blockInstanceKey(block15)).not.toBe(blockInstanceKey(block20));
  });
});
