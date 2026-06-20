import { formatSlotSpeedLabel, slotPreviewPlaybackRate, slotTimestretch } from "./slotSpeed";

describe("slotTimestretch", () => {
  it("computes crop span over target duration", () => {
    expect(slotTimestretch(14.48, 4.0)).toBeCloseTo(3.62, 2);
    expect(slotTimestretch(4.0, 4.0)).toBeCloseTo(1.0, 2);
  });

  it("returns 1 for invalid inputs", () => {
    expect(slotTimestretch(0, 4)).toBe(1);
    expect(slotTimestretch(4, 0)).toBe(1);
  });
});

describe("slotPreviewPlaybackRate", () => {
  it("matches hook unified label speed formula", () => {
    const unifiedSpan = 14.48;
    const hookBudget = 4.0;
    expect(slotPreviewPlaybackRate(unifiedSpan, hookBudget, "hook_start")).toBeCloseTo(
      unifiedSpan / hookBudget,
      4,
    );
  });

  it("includes punch slow-mo factor", () => {
    expect(slotPreviewPlaybackRate(4, 4, "punch")).toBeCloseTo(0.65, 4);
  });
});

describe("formatSlotSpeedLabel", () => {
  it("labels real-time fit near 1x", () => {
    expect(formatSlotSpeedLabel(4, 4, "clip")).toContain("real-time fit");
  });

  it("labels speed up when crop exceeds target", () => {
    expect(formatSlotSpeedLabel(14.48, 4, "hook_end")).toContain("speed up");
  });
});
