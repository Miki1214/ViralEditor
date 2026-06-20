import { useCallback, useEffect, useRef, useState } from "react";
import type { SlotRole } from "../types";
import { slotPreviewPlaybackRate } from "../utils/slotSpeed";

interface ClipCropTimelineProps {
  durationS: number;
  cropStartS: number;
  cropEndS: number;
  targetDurationS: number;
  slotRole?: SlotRole;
  onCropChange: (startS: number, endS: number) => void;
  onCropCommit?: (startS: number, endS: number) => void;
  onDragActiveChange?: (dragging: boolean) => void;
}

type DragMode = "start" | "end" | "range" | null;

export function ClipCropTimeline({
  durationS,
  cropStartS,
  cropEndS,
  targetDurationS,
  slotRole = "clip",
  onCropChange,
  onCropCommit,
  onDragActiveChange,
}: ClipCropTimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const panAnchorRef = useRef<{ anchorTime: number; startS: number; endS: number } | null>(
    null,
  );
  const cropRef = useRef({ startS: cropStartS, endS: cropEndS });
  const [dragging, setDragging] = useState<DragMode>(null);

  cropRef.current = { startS: cropStartS, endS: cropEndS };

  const cropSpanS = Math.max(cropEndS - cropStartS, 0);
  const playbackRate = slotPreviewPlaybackRate(cropSpanS, targetDurationS, slotRole);

  const clampCrop = useCallback(
    (start: number, end: number) => {
      const minSpan = 0.25;
      let s = Math.max(0, Math.min(start, durationS - minSpan));
      let e = Math.max(s + minSpan, Math.min(end, durationS));
      if (e - s < minSpan) {
        e = Math.min(durationS, s + minSpan);
      }
      return { s, e };
    },
    [durationS],
  );

  const clampPan = useCallback(
    (start: number, end: number) => {
      const span = end - start;
      let s = Math.max(0, Math.min(start, durationS - span));
      return { s, e: s + span };
    },
    [durationS],
  );

  const timeFromClientX = useCallback(
    (clientX: number) => {
      const track = trackRef.current;
      if (!track || durationS <= 0) return 0;
      const rect = track.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (clientX - rect.left) / rect.width));
      return ratio * durationS;
    },
    [durationS],
  );

  useEffect(() => {
    onDragActiveChange?.(dragging != null);
  }, [dragging, onDragActiveChange]);

  useEffect(() => {
    if (!dragging) return;

    const onMove = (event: PointerEvent) => {
      const t = timeFromClientX(event.clientX);
      if (dragging === "start") {
        const { s, e } = clampCrop(t, cropEndS);
        onCropChange(s, e);
      } else if (dragging === "end") {
        const { s, e } = clampCrop(cropStartS, t);
        onCropChange(s, e);
      } else if (dragging === "range" && panAnchorRef.current) {
        const { anchorTime, startS, endS } = panAnchorRef.current;
        const delta = t - anchorTime;
        const { s, e } = clampPan(startS + delta, endS + delta);
        onCropChange(s, e);
      }
    };

    const onUp = () => {
      panAnchorRef.current = null;
      setDragging(null);
      const { startS, endS } = cropRef.current;
      onCropCommit?.(startS, endS);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [
    dragging,
    clampCrop,
    clampPan,
    onCropChange,
    onCropCommit,
    timeFromClientX,
    cropEndS,
    cropStartS,
  ]);

  const startPct =
    durationS > 0 ? Math.max(0, Math.min(100, (cropStartS / durationS) * 100)) : 0;
  const endPct =
    durationS > 0 ? Math.max(startPct, Math.min(100, (cropEndS / durationS) * 100)) : 100;

  return (
    <div className="space-y-2">
      <div ref={trackRef} className="crop-slider-track" aria-label="Crop range">
        <div className="crop-slider-shade left-0" style={{ width: `${startPct}%` }} />
        <div className="crop-slider-shade right-0" style={{ width: `${100 - endPct}%` }} />
        <div
          role="slider"
          aria-label="Move crop window"
          aria-valuemin={0}
          aria-valuemax={durationS}
          aria-valuenow={cropStartS}
          className="crop-slider-range"
          style={{
            left: `${startPct}%`,
            width: `${endPct - startPct}%`,
          }}
          onPointerDown={(e) => {
            e.preventDefault();
            panAnchorRef.current = {
              anchorTime: timeFromClientX(e.clientX),
              startS: cropStartS,
              endS: cropEndS,
            };
            setDragging("range");
          }}
        />
        <button
          type="button"
          className="crop-slider-handle"
          style={{ left: `${startPct}%` }}
          onPointerDown={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setDragging("start");
          }}
          aria-label="Crop in"
        />
        <button
          type="button"
          className="crop-slider-handle"
          style={{ left: `${endPct}%` }}
          onPointerDown={(e) => {
            e.preventDefault();
            e.stopPropagation();
            setDragging("end");
          }}
          aria-label="Crop out"
        />
      </div>
      <p className="font-mono text-[11px] text-monitor-muted">
        {cropStartS.toFixed(2)}s → {cropEndS.toFixed(2)}s ({cropSpanS.toFixed(2)}s selected)
        {" · "}
        <span className="text-scope-dim">
          preview at {playbackRate.toFixed(2)}× → {targetDurationS.toFixed(1)}s slot
        </span>
      </p>
    </div>
  );
}
