import { filterBlocksBySlotCount } from "./slotCountFilter";

function makeBlock(overrides: Partial<{ expected_slot_count: number | null }> = {}): {
  id: string;
  start_s: number;
  end_s: number;
  duration_s: number;
  score: number;
  drop_count: number;
  transient_count: number;
  label: string;
  reason: string;
  loop_quality: number;
  phrase_bars: number;
  section_label: string | null;
  key: string | null;
  is_repeated_section: boolean;
  expected_slot_count?: number | null;
} {
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
    ...overrides,
  };
}

describe("filterBlocksBySlotCount", () => {
  it("includes blocks matching selected slot count and excludes others", () => {
    const blocks = [
      makeBlock({ id: "a", expected_slot_count: 3 }),
      makeBlock({ id: "b", expected_slot_count: 5 }),
      makeBlock({ id: "c", expected_slot_count: 8 }),
    ];

    const result = filterBlocksBySlotCount(blocks as typeof blocks, 5);

    expect(result).toHaveLength(1);
    expect(result[0].id).toBe("b");
  });

  it("when no slot filter (null), all blocks pass through unchanged", () => {
    const blocks = [
      makeBlock({ id: "a", expected_slot_count: 3 }),
      makeBlock({ id: "b", expected_slot_count: 5 }),
    ];

    const result = filterBlocksBySlotCount(blocks as typeof blocks, null);

    expect(result).toHaveLength(2);
    expect(result.map((b) => b.id)).toEqual(["a", "b"]);
  });

  it("handles empty block list gracefully", () => {
    const result = filterBlocksBySlotCount([], 5);
    expect(result).toHaveLength(0);
  });
});
