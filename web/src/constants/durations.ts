export const TARGET_DURATION_PRESETS = [
  { label: "5s", value: 5 },
  { label: "10s", value: 10 },
  { label: "15s", value: 15 },
  { label: "20s", value: 20 },
  { label: "25s", value: 25 },
  { label: "30s", value: 30 },
  { label: "45s", value: 45 },
  { label: "60s", value: 60 },
] as const;

export const TARGET_DURATION_PRESET_VALUES = TARGET_DURATION_PRESETS.map((p) => p.value);

export const DEFAULT_TARGET_DURATION_S = 10;

export const CUSTOM_DURATION_MIN_S = 3;
export const CUSTOM_DURATION_MAX_S = 120;

export function isPresetTargetDuration(seconds: number): boolean {
  return (TARGET_DURATION_PRESET_VALUES as readonly number[]).includes(seconds);
}

export const SLOT_COUNT_PRESETS = Array.from({ length: 10 }, (_, i) => ({
  label: `${i + 1} slot${i + 1 > 1 ? "s" : ""}`,
  value: i + 1,
})) as const;
