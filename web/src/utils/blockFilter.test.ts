import { filterBlocks } from "./blockFilter";
import type { MusicBlock } from "../types";

function makeBlock(
  overrides: Partial<MusicBlock> = {},
): MusicBlock {
  return {
    id: "blk-000",
    start_s: 0,
    end_s: 10,
    duration_s: 10,
    score: 0.8,
    drop_count: 2,
    transient_count: 3,
    label: "test",
    reason: "score",
    loop_quality: 0.9,
    phrase_bars: 4,
    section_label: null,
    key: null,
    is_repeated_section: false,
    expected_slot_count: 3,
    preset_target_duration_s: 10,
    ...overrides,
  };
}

describe("filterBlocks", () => {
  const pool = [
    makeBlock({ id: "a", preset_target_duration_s: 10, expected_slot_count: 2 }),
    makeBlock({ id: "b", preset_target_duration_s: 10, expected_slot_count: 4 }),
    makeBlock({ id: "c", preset_target_duration_s: 15, expected_slot_count: 4 }),
    makeBlock({ id: "d", preset_target_duration_s: 20, expected_slot_count: 5 }),
  ];

  it("includes all blocks when both filters are Any", () => {
    const result = filterBlocks(pool, null, null);
    expect(result).toHaveLength(4);
    expect(result.map((b) => b.id)).toEqual(["a", "b", "c", "d"]);
  });

  it("filters by target duration only (slot Any)", () => {
    const result = filterBlocks(pool, 10, null);
    expect(result).toHaveLength(2);
    expect(result.map((b) => b.id)).toEqual(["a", "b"]);
  });

  it("filters by slot count only (target Any)", () => {
    const result = filterBlocks(pool, null, 4);
    expect(result).toHaveLength(2);
    expect(result.map((b) => b.id)).toEqual(["b", "c"]);
  });

  it("filters by both target duration and slot count (AND)", () => {
    const result = filterBlocks(pool, 15, 4);
    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("c");
  });

  it("returns empty when no block matches both filters", () => {
    const result = filterBlocks(pool, 10, 5);
    expect(result).toHaveLength(0);
  });

  it("returns empty when all_blocks is empty and both Any", () => {
    const result = filterBlocks([], null, null);
    expect(result).toHaveLength(0);
  });
});
