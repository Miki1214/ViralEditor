import type { StoryboardPayload, StorySlot } from "../types";

/** Matches composite xfade duration in proxy_render.build_composite_filtergraph */
export const COMPOSITE_XFADE_S = 0.25;

function assignedSlots(storyboard: StoryboardPayload): StorySlot[] {
  return [...storyboard.slots]
    .sort((a, b) => a.order - b.order)
    .filter((slot) => slot.assigned_clip_id);
}

function videoStartForAssignedIndex(assigned: StorySlot[], index: number): number {
  let videoStart = 0;
  for (let i = 0; i < index; i++) {
    videoStart += assigned[i].target_duration_s;
    if (i + 1 < assigned.length && assigned[i + 1].transition_in === "xfade") {
      videoStart -= COMPOSITE_XFADE_S;
    }
  }
  return videoStart;
}

export function compositeVideoTimeToBlockPlayhead(
  videoTimeS: number,
  storyboard: StoryboardPayload,
): number {
  const assigned = assignedSlots(storyboard);

  if (assigned.length === 0) {
    return Math.max(0, Math.min(videoTimeS, storyboard.total_duration_s));
  }

  let videoStart = 0;
  for (let i = 0; i < assigned.length; i++) {
    const slot = assigned[i];
    const len = slot.target_duration_s;
    const videoEnd = videoStart + len;

    if (videoTimeS < videoEnd || i === assigned.length - 1) {
      const localT = Math.max(0, Math.min(len, videoTimeS - videoStart));
      const slotSpan = slot.out_end_s - slot.out_start_s;
      return slot.out_start_s + (len > 0 ? (localT / len) * slotSpan : 0);
    }

    videoStart = videoEnd;
    if (i + 1 < assigned.length && assigned[i + 1].transition_in === "xfade") {
      videoStart -= COMPOSITE_XFADE_S;
    }
  }

  return assigned[assigned.length - 1].out_end_s;
}

export function blockPlayheadToCompositeVideoTime(
  playheadS: number,
  storyboard: StoryboardPayload,
): number {
  const assigned = assignedSlots(storyboard);
  if (assigned.length === 0) {
    return Math.max(0, playheadS);
  }

  for (let i = 0; i < assigned.length; i++) {
    const slot = assigned[i];
    const inSlot =
      playheadS >= slot.out_start_s - 1e-6 &&
      (playheadS < slot.out_end_s - 1e-6 || i === assigned.length - 1);
    if (!inSlot) continue;

    const slotSpan = slot.out_end_s - slot.out_start_s;
    const ratio =
      slotSpan > 0
        ? Math.max(0, Math.min(1, (playheadS - slot.out_start_s) / slotSpan))
        : 0;
    return videoStartForAssignedIndex(assigned, i) + ratio * slot.target_duration_s;
  }

  return 0;
}
