import { describe, expect, it } from "vitest";
import {
  countSpatialFxMarkers,
  planSpatialFxMarkers,
  type FxMarker,
} from "./spatialFxMarkers";
import type { ScopeLaneSeries, Transient } from "../types";

function lane(id: string, values: Array<[number, number]>): ScopeLaneSeries {
  return {
    id,
    label: id,
    points: values.map(([t, v]) => ({ t, v })),
  };
}

const panDefaults = {
  translateEnabled: true,
  panBeatMode: "beats" as const,
  panEnergyThreshold: 0.45,
  panEnergyFloor: 0.2,
  panHookEnabled: true,
  panHookByS: 1.0,
};

describe("spatialFxMarkers translate", () => {
  const musicStartS = 0;
  const musicEndS = 4;
  const downbeats = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5];
  const beats = [0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0];
  const lanes: ScopeLaneSeries[] = [
    lane("rms", Array.from({ length: 40 }, (_, index) => [index * 0.1, 0.8])),
    lane("band_low", Array.from({ length: 40 }, (_, index) => [index * 0.1, 0.7])),
    lane("surge", Array.from({ length: 40 }, (_, index) => [index * 0.1, 0.5])),
    lane("build", []),
    lane("drop_salience", []),
    lane("flux_low", []),
    lane("flux_high", []),
  ];

  it("plans alternating translate markers on beats", () => {
    const markers = planSpatialFxMarkers([] as Transient[], {
      musicStartS,
      musicEndS,
      maxEventsPerSecond: 16,
      enabled: true,
      lanes,
      downbeats,
      beats,
      pan: panDefaults,
    });
    const pans = markers.filter((marker) => marker.kind === "translate");
    expect(pans.length).toBeGreaterThanOrEqual(2);
    expect(pans[0].direction).toBe(1);
    expect(pans[1].direction).toBe(-1);
  });

  it("guarantees hook pan within configured window", () => {
    const quietLanes: ScopeLaneSeries[] = [
      lane("rms", Array.from({ length: 40 }, (_, index) => [index * 0.1, 0.05])),
      lane("band_low", Array.from({ length: 40 }, (_, index) => [index * 0.1, 0.05])),
      lane("surge", Array.from({ length: 40 }, (_, index) => [index * 0.1, 0.05])),
    ];
    const markers = planSpatialFxMarkers([] as Transient[], {
      musicStartS,
      musicEndS: 3,
      maxEventsPerSecond: 16,
      enabled: true,
      lanes: quietLanes,
      downbeats: [1.5, 2.0, 2.5],
      beats: [1.5, 2.0, 2.5],
      pan: {
        ...panDefaults,
        panEnergyFloor: 0.9,
        panHookByS: 1.0,
      },
    });
    const pans = markers.filter((marker) => marker.kind === "translate");
    expect(pans.some((marker) => marker.timeS <= 1.0)).toBe(true);
    expect(pans.some((marker) => marker.reason?.includes("Hook pan"))).toBe(true);
  });

  it("skips hook pan when disabled", () => {
    const quietLanes: ScopeLaneSeries[] = [
      lane("rms", Array.from({ length: 40 }, (_, index) => [index * 0.1, 0.05])),
      lane("band_low", Array.from({ length: 40 }, (_, index) => [index * 0.1, 0.05])),
      lane("surge", Array.from({ length: 40 }, (_, index) => [index * 0.1, 0.05])),
    ];
    const markers = planSpatialFxMarkers([] as Transient[], {
      musicStartS,
      musicEndS: 3,
      maxEventsPerSecond: 16,
      enabled: true,
      lanes: quietLanes,
      downbeats: [1.5, 2.0, 2.5],
      beats: [1.5, 2.0, 2.5],
      pan: {
        ...panDefaults,
        panEnergyFloor: 0.9,
        panHookEnabled: false,
        panHookByS: 1.0,
      },
    });
    const pans = markers.filter((marker) => marker.kind === "translate");
    expect(pans.some((marker) => marker.reason?.includes("Hook pan"))).toBe(false);
  });

  it("counts translate markers separately from zoom and rotate", () => {
    const markers: FxMarker[] = [
      { timeS: 0.5, kind: "zoom", magnitude: 1.07 },
      { timeS: 1.0, kind: "rotate", magnitude: 1.2 },
      { timeS: 1.5, kind: "translate", magnitude: 0.8, direction: 1 },
      { timeS: 2.0, kind: "translate", magnitude: 0.8, direction: -1 },
    ];
    expect(countSpatialFxMarkers(markers)).toEqual({
      zoom: 1,
      rotate: 1,
      translate: 2,
    });
  });
});
