import { useCallback, useEffect, useRef, useState } from "react";
import type { SpatialCrop } from "../types";
import {
  clampCropBox,
  defaultPortraitCrop,
  effectiveVideoSize,
  normalizedToPixelRect,
  objectContainRect,
  pixelRectToNormalized,
  resizeCropByDelta,
  type PixelRect,
} from "../utils/spatialCrop";

interface SpatialCropModalProps {
  open: boolean;
  videoUrl: string;
  rotationDeg: number;
  initialCrop: SpatialCrop | null;
  onApply: (crop: SpatialCrop | null) => void;
  onClose: () => void;
}

type DragMode = "move" | "resize-se" | "resize-nw" | null;

export function SpatialCropModal({
  open,
  videoUrl,
  rotationDeg,
  initialCrop,
  onApply,
  onClose,
}: SpatialCropModalProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const dragAnchorRef = useRef<{ mode: DragMode; startX: number; startY: number; box: PixelRect }>(
    null,
  );

  const [videoSize, setVideoSize] = useState({ width: 0, height: 0 });
  const [stageSize, setStageSize] = useState({ width: 0, height: 0 });
  const [cropBox, setCropBox] = useState<PixelRect | null>(null);
  const [dragging, setDragging] = useState<DragMode>(null);
  const videoBoundsRef = useRef<PixelRect>({ x: 0, y: 0, w: 0, h: 0 });
  const prevBoundsRef = useRef<PixelRect>({ x: 0, y: 0, w: 0, h: 0 });
  const openSessionRef = useRef<string | null>(null);

  const frame = effectiveVideoSize(videoSize.width, videoSize.height, rotationDeg);
  const videoBounds = objectContainRect(stageSize.width, stageSize.height, frame.width, frame.height);
  videoBoundsRef.current = videoBounds;

  const syncLayout = useCallback(() => {
    const stage = stageRef.current;
    const video = videoRef.current;
    if (!stage) return;
    const rect = stage.getBoundingClientRect();
    setStageSize({ width: rect.width, height: rect.height });
    if (video && video.videoWidth > 0 && video.videoHeight > 0) {
      setVideoSize({ width: video.videoWidth, height: video.videoHeight });
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    syncLayout();
    const stage = stageRef.current;
    if (!stage) return;
    const observer = new ResizeObserver(() => syncLayout());
    observer.observe(stage);
    return () => observer.disconnect();
  }, [open, syncLayout, rotationDeg, videoUrl]);

  useEffect(() => {
    if (!open) {
      openSessionRef.current = null;
      setCropBox(null);
      return;
    }
    const session = `${videoUrl}|${rotationDeg}|${JSON.stringify(initialCrop)}`;
    if (openSessionRef.current === session) return;
    openSessionRef.current = session;
    setCropBox(null);
  }, [open, videoUrl, rotationDeg, initialCrop]);

  useEffect(() => {
    if (!open || dragging || videoBounds.w <= 0 || videoBounds.h <= 0) return;

    setCropBox((prev) => {
      if (prev != null) return prev;
      return initialCrop
        ? normalizedToPixelRect(initialCrop, videoBounds)
        : defaultPortraitCrop(videoBounds);
    });
  }, [open, dragging, initialCrop, videoBounds.x, videoBounds.y, videoBounds.w, videoBounds.h]);

  useEffect(() => {
    if (!open || dragging || videoBounds.w <= 0 || videoBounds.h <= 0) {
      prevBoundsRef.current = videoBounds;
      return;
    }

    const prev = prevBoundsRef.current;
    const boundsChanged =
      prev.w > 0 &&
      (prev.x !== videoBounds.x ||
        prev.y !== videoBounds.y ||
        prev.w !== videoBounds.w ||
        prev.h !== videoBounds.h);

    if (boundsChanged) {
      setCropBox((current) => {
        if (current == null) return current;
        const norm = pixelRectToNormalized(current, prev);
        return normalizedToPixelRect(norm, videoBounds);
      });
    }
    prevBoundsRef.current = videoBounds;
  }, [open, dragging, videoBounds.x, videoBounds.y, videoBounds.w, videoBounds.h]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  useEffect(() => {
    if (!dragging) return;

    const onMove = (event: PointerEvent) => {
      const anchor = dragAnchorRef.current;
      const bounds = videoBoundsRef.current;
      if (!anchor || bounds.w <= 0) return;

      const dx = event.clientX - anchor.startX;
      const dy = event.clientY - anchor.startY;

      if (anchor.mode === "move") {
        setCropBox(
          clampCropBox(
            {
              x: anchor.box.x + dx,
              y: anchor.box.y + dy,
              w: anchor.box.w,
              h: anchor.box.h,
            },
            bounds,
          ),
        );
      } else if (anchor.mode === "resize-se") {
        setCropBox(resizeCropByDelta(anchor.box, dx, dy, bounds, "se"));
      } else if (anchor.mode === "resize-nw") {
        setCropBox(resizeCropByDelta(anchor.box, dx, dy, bounds, "nw"));
      }
    };

    const onUp = () => {
      dragAnchorRef.current = null;
      setDragging(null);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [dragging]);

  const startDrag = (mode: DragMode, event: React.PointerEvent) => {
    if (!cropBox) return;
    event.preventDefault();
    event.stopPropagation();
    event.currentTarget.setPointerCapture(event.pointerId);
    dragAnchorRef.current = {
      mode,
      startX: event.clientX,
      startY: event.clientY,
      box: cropBox,
    };
    setDragging(mode);
  };

  const handleApply = () => {
    if (!cropBox || videoBounds.w <= 0) {
      onApply(null);
      return;
    }
    const norm = pixelRectToNormalized(cropBox, videoBounds);
    onApply(norm);
  };

  if (!open) return null;

  const shade = cropBox
    ? {
        top: cropBox.y,
        left: cropBox.x,
        width: cropBox.w,
        height: cropBox.h,
      }
    : null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="presentation">
      <button
        type="button"
        className="absolute inset-0 bg-monitor-bg/80 backdrop-blur-sm"
        aria-label="Close frame crop"
        onClick={onClose}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="spatial-crop-title"
        className="panel relative z-10 flex w-full max-w-3xl flex-col gap-4 p-5 shadow-xl"
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <h2 id="spatial-crop-title" className="text-sm font-semibold tracking-tight">
              Frame crop
            </h2>
            <p className="mt-1 text-xs text-monitor-muted">
              Drag the 9:16 window or resize from corners. Only the area inside the frame is kept.
            </p>
          </div>
          <button type="button" className="btn-ghost text-xs" onClick={onClose}>
            Cancel
          </button>
        </div>

        <div
          ref={stageRef}
          className="relative mx-auto aspect-[9/16] w-full max-h-[min(72vh,720px)] overflow-hidden rounded border border-monitor-border bg-black"
        >
          <video
            ref={videoRef}
            key={videoUrl}
            src={videoUrl}
            className="pointer-events-none absolute inset-0 h-full w-full object-contain"
            style={{ transform: `rotate(${rotationDeg}deg)` }}
            muted
            playsInline
            onLoadedMetadata={(event) => {
              const el = event.currentTarget;
              setVideoSize({ width: el.videoWidth, height: el.videoHeight });
              syncLayout();
            }}
          />

          {shade && stageSize.width > 0 && (
            <>
              <div
                className="pointer-events-none absolute left-0 right-0 top-0 bg-black/55"
                style={{ height: shade.top }}
              />
              <div
                className="pointer-events-none absolute left-0 right-0 bg-black/55"
                style={{ top: shade.top + shade.height, bottom: 0 }}
              />
              <div
                className="pointer-events-none absolute bg-black/55"
                style={{
                  top: shade.top,
                  left: 0,
                  width: shade.left,
                  height: shade.height,
                }}
              />
              <div
                className="pointer-events-none absolute bg-black/55"
                style={{
                  top: shade.top,
                  left: shade.left + shade.width,
                  right: 0,
                  height: shade.height,
                }}
              />
              <div
                className="absolute cursor-move border-2 border-scope-trace shadow-[0_0_0_1px_rgba(0,0,0,0.5)]"
                style={{
                  left: shade.left,
                  top: shade.top,
                  width: shade.width,
                  height: shade.height,
                }}
                onPointerDown={(event) => startDrag("move", event)}
              >
                <span className="pointer-events-none absolute left-1 top-1 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[9px] uppercase text-scope-trace">
                  9:16
                </span>
                <button
                  type="button"
                  aria-label="Resize top-left"
                  className="absolute -left-1.5 -top-1.5 h-3.5 w-3.5 cursor-nwse-resize rounded-full border border-scope-trace bg-monitor-bg"
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    startDrag("resize-nw", event);
                  }}
                />
                <button
                  type="button"
                  aria-label="Resize bottom-right"
                  className="absolute -bottom-1.5 -right-1.5 h-3.5 w-3.5 cursor-nwse-resize rounded-full border border-scope-trace bg-monitor-bg"
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    startDrag("resize-se", event);
                  }}
                />
              </div>
            </>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <button
            type="button"
            className="btn-ghost text-xs"
            onClick={() => setCropBox(defaultPortraitCrop(videoBounds))}
          >
            Reset crop
          </button>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn-ghost text-xs"
              onClick={() => onApply(null)}
            >
              Clear crop
            </button>
            <button type="button" className="btn-primary text-xs" onClick={handleApply}>
              Apply crop
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
