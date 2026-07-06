import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { AudioScopePanel } from "./AudioScopePanel";
import { SLOT_ANY_CHIP_ID, TARGET_ANY_CHIP_ID } from "./audioScopeHelpers";
import type { MusicBlock, WaveformPayload } from "../types";

const scopeCanvasBlocks = vi.hoisted(() => ({ current: [] as MusicBlock[] }));

vi.mock("./ScopeCanvas", () => ({
  ScopeCanvas: ({ blocks }: { blocks: MusicBlock[] }) => {
    scopeCanvasBlocks.current = blocks;
    return <div data-testid="scope-canvas" />;
  },
  blockPixelRange: () => ({ startX: 0, endX: 100, canvasWidth: 960 }),
  scopeWidth: () => 960,
}));

vi.mock("./MusicBlockCard", () => ({
  MusicBlockCard: ({ block }: { block: { id: string } }) => (
    <div data-testid={`block-${block.id}`} />
  ),
}));

vi.mock("./scope/MusicDetailRack", () => ({
  MusicDetailRackToggle: () => null,
  MusicDetailRackChart: () => null,
  musicDetailHasContent: () => false,
  musicDetailLaneCount: () => 0,
}));

vi.mock("./scope/ScopeLegend", () => ({
  ScopeLegend: () => null,
}));

function makeWaveform(overrides: Partial<WaveformPayload> = {}): WaveformPayload {
  return {
    duration_s: 60,
    global_bpm: 128,
    key: "C",
    beat_engine: "librosa",
    points: [{ t: 0, v: 0.5 }],
    transients: [],
    beats: [],
    downbeats: [],
    sections: [],
    lanes: [],
    chroma: null,
    blocks: [
      {
        id: "block_a",
        start_s: 0,
        end_s: 10,
        duration_s: 10,
        score: 0.9,
        drop_count: 1,
        transient_count: 1,
        label: "A",
        reason: "test",
        loop_quality: 0.8,
        phrase_bars: 4,
        section_label: null,
        key: "C",
        is_repeated_section: false,
        expected_slot_count: 2,
        preset_target_duration_s: 10,
      },
    ],
    all_blocks: [
      {
        id: "block_a",
        start_s: 0,
        end_s: 10,
        duration_s: 10,
        score: 0.9,
        drop_count: 1,
        transient_count: 1,
        label: "A",
        reason: "test",
        loop_quality: 0.8,
        phrase_bars: 4,
        section_label: null,
        key: "C",
        is_repeated_section: false,
        expected_slot_count: 2,
        preset_target_duration_s: 10,
      },
      {
        id: "block_b",
        start_s: 5,
        end_s: 20,
        duration_s: 15,
        score: 0.85,
        drop_count: 1,
        transient_count: 2,
        label: "B",
        reason: "test",
        loop_quality: 0.75,
        phrase_bars: 4,
        section_label: null,
        key: "C",
        is_repeated_section: false,
        expected_slot_count: 4,
        preset_target_duration_s: 15,
      },
    ],
    selected_block_id: null,
    matchable_target_durations_s: [5, 10, 15, 20],
    target_loop_qualities: [
      { target_duration_s: 10, loop_quality_pct: 70 },
      { target_duration_s: 15, loop_quality_pct: 80 },
    ],
    ...overrides,
  };
}

function renderPanel(overrides: {
  targetDurationFilter?: number | null;
  onTargetDurationFilterChange?: (value: number | null) => void;
  selectedSlotCount?: number | null;
  onSlotCountChange?: (value: number | null) => void;
} = {}) {
  const onTargetDurationFilterChange = overrides.onTargetDurationFilterChange ?? vi.fn();
  const onSlotCountChange = overrides.onSlotCountChange ?? vi.fn();
  const onTargetChange = vi.fn();
  const onSelectBlock = vi.fn();

  render(
    <AudioScopePanel
      jobId="job-1"
      waveform={makeWaveform()}
      targetDurationS={10}
      useFullTrack={false}
      selectedBlockId={null}
      onTargetChange={onTargetChange}
      onSelectBlock={onSelectBlock}
      targetDurationFilter={overrides.targetDurationFilter ?? null}
      onTargetDurationFilterChange={onTargetDurationFilterChange}
      selectedSlotCount={overrides.selectedSlotCount ?? null}
      onSlotCountChange={onSlotCountChange}
    />,
  );

  return { onTargetDurationFilterChange, onSlotCountChange, onTargetChange };
}

describe("AudioScopePanel Any filters", () => {
  it("renders Any chip on Target Short Length row", () => {
    renderPanel();
    expect(document.getElementById(TARGET_ANY_CHIP_ID)).toBeInTheDocument();
  });

  it("renders Any chip on Slots row", () => {
    renderPanel();
    expect(document.getElementById(SLOT_ANY_CHIP_ID)).toBeInTheDocument();
  });

  it("clicking Any chip on Target row calls onTargetDurationFilterChange(null)", () => {
    const { onTargetDurationFilterChange } = renderPanel({ targetDurationFilter: 10 });
    fireEvent.click(document.getElementById(TARGET_ANY_CHIP_ID)!);
    expect(onTargetDurationFilterChange).toHaveBeenCalledWith(null);
  });

  it("clicking Any chip on Slots row calls onSlotCountChange(null)", () => {
    const { onSlotCountChange } = renderPanel({ selectedSlotCount: 4 });
    fireEvent.click(document.getElementById(SLOT_ANY_CHIP_ID)!);
    expect(onSlotCountChange).toHaveBeenCalledWith(null);
  });

  it("does not render Clear button", () => {
    renderPanel({ selectedSlotCount: 4 });
    expect(screen.queryByRole("button", { name: "Clear" })).not.toBeInTheDocument();
  });
});

describe("AudioScopePanel canvas block filtering", () => {
  it("passes only target-duration-filtered blocks to ScopeCanvas", () => {
    renderPanel({ targetDurationFilter: 10 });
    expect(scopeCanvasBlocks.current.map((block) => block.id)).toEqual(["block_a"]);
    expect(screen.getByTestId("block-block_a")).toBeInTheDocument();
    expect(screen.queryByTestId("block-block_b")).not.toBeInTheDocument();
  });

  it("passes only slot-count-filtered blocks to ScopeCanvas", () => {
    renderPanel({ selectedSlotCount: 4 });
    expect(scopeCanvasBlocks.current.map((block) => block.id)).toEqual(["block_b"]);
    expect(screen.getByTestId("block-block_b")).toBeInTheDocument();
    expect(screen.queryByTestId("block-block_a")).not.toBeInTheDocument();
  });

  it("passes all catalog blocks to ScopeCanvas when both filters are Any", () => {
    renderPanel();
    expect(scopeCanvasBlocks.current.map((block) => block.id)).toEqual([
      "block_a",
      "block_b",
    ]);
  });
});
