import { useCallback, useEffect, useRef, useState } from "react";
import type { SpatialCrop } from "../types";
import {
  clampCropBoxFree,
  defaultPortraitCrop,
  effectiveVideoSize,
  letterboxStrips,
  normalizedToPixelRect,
  objectContainRect,
  pixelRectToNormalized,
  rotatedVideoDisplayStyle,
  resizeCropByDeltaFree,
  type PixelRect,
} from "../utils/spatialCrop";

interface SpatialCropModalProps {
  open: boolean;
  slotId: string;
  videoUrl: string;
  rotationDeg: number;
  initialCrop: SpatialCrop | null;
  onApply: (crop: SpatialCrop | null) => void;
  onClose: () => void;
}

type DragMode = "move" | "resize-se" | "resize-nw" | null;

const ZOOM_MIN = 0.5;
const ZOOM_MAX = 3;
const ZOOM_STEP = 0.25;

function clampZoom(value: number): number {
  const stepped = Math.round(value / ZOOM_STEP) * ZOOM_STEP;
  return Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, stepped));
}

export function SpatialCropModal({
  open,
  slotId,
  videoUrl,
  rotationDeg,
  initialCrop,
  onApply,
  onClose,
}: SpatialCropModalProps) {
  const stageRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const dragAnchorRef = useRef<{ mode: DragMode; startX: number; startY: number; box: PixelRect }>(
    null,
  );

  const [videoSize, setVideoSize] = useState({ width: 0, height: 0 });
  const [stageSize, setStageSize] = useState({ width: 0, height: 0 });
  const [cropBox, setCropBox] = useState<PixelRect | null>(null);
  const [dragging, setDragging] = useState<DragMode>(null);
  const [zoom, setZoom] = useState(1);
  const videoBoundsRef = useRef<PixelRect>({ x: 0, y: 0, w: 0, h: 0 });
  const prevStageSizeRef = useRef({ width: 0, height: 0 });
  const sessionRef = useRef<string | null>(null);
  const cropInitializedRef = useRef(false);

  const sessionKey = `${slotId}|${videoUrl}|${rotationDeg}|${JSON.stringify(initialCrop)}`;

  const frame = effectiveVideoSize(videoSize.width, videoSize.height, rotationDeg);
  const videoBounds = objectContainRect(stageSize.width, stageSize.height, frame.width, frame.height);
  const stageBounds: PixelRect = { x: 0, y: 0, w: stageSize.width, h: stageSize.height };
  videoBoundsRef.current = videoBounds;

  const syncLayout = useCallback(() => {
    const stage = stageRef.current;
    const video = videoRef.current;
    if (!stage) return;
    setStageSize({ width: stage.offsetWidth, height: stage.offsetHeight });
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
      sessionRef.current = null;
      cropInitializedRef.current = false;
      setCropBox(null);
      setVideoSize({ width: 0, height: 0 });
      setZoom(1);
      return;
    }
    if (sessionRef.current === sessionKey) return;
    sessionRef.current = sessionKey;
    cropInitializedRef.current = false;
    setCropBox(null);
    setVideoSize({ width: 0, height: 0 });
    setZoom(1);
    prevStageSizeRef.current = { width: 0, height: 0 };
  }, [open, sessionKey]);

  useEffect(() => {
    if (
      !open ||
      dragging ||
      cropInitializedRef.current ||
      sessionRef.current !== sessionKey ||
      videoSize.width <= 0 ||
      videoBounds.w <= 0 ||
      videoBounds.h <= 0
    ) {
      return;
    }

    cropInitializedRef.current = true;
    setCropBox(
      initialCrop
        ? normalizedToPixelRect(initialCrop, videoBounds)
        : defaultPortraitCrop(stageBounds),
    );
    prevStageSizeRef.current = { width: stageSize.width, height: stageSize.height };
  }, [
    open,
    dragging,
    sessionKey,
    initialCrop,
    videoSize.width,
    videoSize.height,
    stageSize.width,
    stageSize.height,
    videoBounds.x,
    videoBounds.y,
    videoBounds.w,
    videoBounds.h,
  ]);

  useEffect(() => {
    if (
      !open ||
      dragging ||
      !cropInitializedRef.current ||
      sessionRef.current !== sessionKey ||
      stageSize.width <= 0 ||
      stageSize.height <= 0
    ) {
      return;
    }

    const prev = prevStageSizeRef.current;
    const stageResized =
      prev.width > 0 &&
      (prev.width !== stageSize.width || prev.height !== stageSize.height);

    if (stageResized) {
      const prevStage: PixelRect = { x: 0, y: 0, w: prev.width, h: prev.height };
      setCropBox((current) => {
        if (current == null) return current;
        const norm = pixelRectToNormalized(current, prevStage);
        return normalizedToPixelRect(norm, stageBounds);
      });
    }
    prevStageSizeRef.current = { width: stageSize.width, height: stageSize.height };
  }, [open, dragging, sessionKey, stageSize.width, stageSize.height, stageBounds.w, stageBounds.h]);

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
      const stage = { x: 0, y: 0, w: stageSize.width, h: stageSize.height };
      if (!anchor || stage.w <= 0) return;

      const dx = (event.clientX - anchor.startX) / zoom;
      const dy = (event.clientY - anchor.startY) / zoom;

      if (anchor.mode === "move") {
        setCropBox(
          clampCropBoxFree(
            {
              x: anchor.box.x + dx,
              y: anchor.box.y + dy,
              w: anchor.box.w,
              h: anchor.box.h,
            },
            stage,
          ),
        );
      } else if (anchor.mode === "resize-se") {
        setCropBox(resizeCropByDeltaFree(anchor.box, dx, dy, stage, "se"));
      } else if (anchor.mode === "resize-nw") {
        setCropBox(resizeCropByDeltaFree(anchor.box, dx, dy, stage, "nw"));
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
  }, [dragging, stageSize.width, stageSize.height, zoom]);

  const adjustZoom = (delta: number) => {
    setZoom((current) => clampZoom(current + delta));
  };

  const handleViewportWheel = (event: React.WheelEvent<HTMLDivElement>) => {
    if (!event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    adjustZoom(event.deltaY < 0 ? ZOOM_STEP : -ZOOM_STEP);
  };

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

  const stageAspect = "9 / 16";
  const videoStyle =
    videoBounds.w > 0 && frame.width > 0
      ? rotatedVideoDisplayStyle(videoBounds, rotationDeg)
      : null;

  const shade = cropBox
    ? {
        top: cropBox.y,
        left: cropBox.x,
        width: cropBox.w,
        height: cropBox.h,
      }
    : null;

  return (
    <div id="spatial-crop-overlay" className="fixed inset-0 z-50 flex items-center justify-center p-4" role="presentation">
      <button
        id="spatial-crop-close-btn"
        type="button"
        className="absolute inset-0 bg-monitor-bg/80 backdrop-blur-sm"
        aria-label="Close frame crop"
        onClick={onClose}
      />
      <div
        id="spatial-crop-dialog"
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
            <p id="spatial-crop-desc" className="mt-1 text-xs text-monitor-muted">
              Drag or resize the 9:16 window. Extend past the video to add black bars in the output. Use
              zoom controls or Ctrl+scroll for fine adjustments.
            </p>
          </div>
          <button id="spatial-crop-cancel-btn" type="button" className="btn-ghost text-xs" onClick={onClose}>
            Cancel
          </button>
        </div>

        <div
          id="spatial-crop-viewport"
          ref={viewportRef}
          className="mx-auto max-h-[min(72vh,720px)] max-w-full overflow-auto rounded border border-monitor-border bg-black"
          onWheel={handleViewportWheel}
        >
          <div
            id="spatial-crop-stage"
            className="relative"
            style={
              stageSize.width > 0 && stageSize.height > 0
                ? {
                    width: stageSize.width * zoom,
                    height: stageSize.height * zoom,
                  }
                : undefined
            }
          >
            <div
              ref={stageRef}
              className="relative h-[min(72vh,720px)] w-auto overflow-hidden bg-black"
              style={{
                aspectRatio: stageAspect,
                transform: `scale(${zoom})`,
                transformOrigin: "0 0",
              }}
            >
          <video
            id="spatial-crop-video"
            ref={videoRef}
            key={videoUrl}
            src={videoUrl}
            className="pointer-events-none absolute object-fill"
            style={
              videoStyle
                ? {
                    left: videoStyle.left,
                    top: videoStyle.top,
                    width: videoStyle.width,
                    height: videoStyle.height,
                    transform: videoStyle.transform,
                  }
                : {
                    opacity: 0,
                    width: 1,
                    height: 1,
                    left: 0,
                    top: 0,
                  }
            }
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
              <div id="spatial-crop-shade-top" className="pointer-events-none absolute left-0 right-0 top-0 bg-black/55" style={{ height: shade.top }} />
              <div id="spatial-crop-shade-bottom" className="pointer-events-none absolute left-0 right-0 bg-black/55" style={{ top: shade.top + shade.height, bottom: 0 }} />
              <div id="spatial-crop-shade-left" className="pointer-events-none absolute bg-black/55" style={{ top: shade.top, left: 0, width: shade.left, height: shade.height }} />
              <div id="spatial-crop-shade-right" className="pointer-events-none absolute bg-black/55" style={{ top: shade.top, left: shade.left + shade.width, right: 0, height: shade.height }} />
              {letterboxStrips(
                { x: shade.left, y: shade.top, w: shade.width, h: shade.height },
                videoBounds,
              ).map((strip, index) => (
                <div id={`spatial-crop-letterbox-${index}`} key={`letterbox-${index}`} className="pointer-events-none absolute bg-black" style={{ left: strip.x, top: strip.y, width: strip.w, height: strip.h }} />
              ))}
              <div id="spatial-crop-box" className="absolute cursor-move border-2 border-scope-trace shadow-[0_0_0_1px_rgba(0,0,0,0.5)]" style={{ left: shade.left, top: shade.top, width: shade.width, height: shade.height }} onPointerDown={(event) => startDrag("move", event)}>
                <span id="spatial-crop-label-916" className="pointer-events-none absolute left-1 top-1 rounded bg-black/60 px-1.5 py-0.5 font-mono text-[9px] uppercase text-scope-trace">
                  9:16
                </span>
                <button id="spatial-crop-resize-nw" type="button" aria-label="Resize top-left" className="absolute -left-1.5 -top-1.5 h-3.5 w-3.5 cursor-nwse-resize rounded-full border border-scope-trace bg-monitor-bg" onPointerDown={(event) => { event.stopPropagation(); startDrag("resize-nw", event); }} />
                <button id="spatial-crop-resize-se" type="button" aria-label="Resize bottom-right" className="absolute -bottom-1.5 -right-1.5 h-3.5 w-3.5 cursor-nwse-resize rounded-full border border-scope-trace bg-monitor-bg" onPointerDown={(event) => { event.stopPropagation(); startDrag("resize-se", event); }} />
              </div>
            </>
          )}
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap gap-2">
            <button id="spatial-crop-reset-btn" type="button" className="btn-ghost text-xs" onClick={() => setCropBox(defaultPortraitCrop(stageBounds))}>
              Reset crop
            </button>
            <button id="spatial-crop-fit-btn" type="button" className="btn-ghost text-xs" disabled={videoBounds.w <= 0 || videoBounds.h <= 0} onClick={() => setCropBox(defaultPortraitCrop(videoBounds))}>
              Fit to video
            </button>
          </div>
          <div id="spatial-crop-zoom-group" className="flex items-center gap-1 rounded border border-monitor-border bg-monitor-bg/40 px-1" role="group" aria-label="Preview zoom">
            <button id="spatial-crop-zoom-out" type="button" className="btn-ghost px-2 py-1 font-mono text-xs" aria-label="Zoom out" disabled={zoom <= ZOOM_MIN} onClick={() => adjustZoom(-ZOOM_STEP)}>
              −
            </button>
            <button id="spatial-crop-zoom-reset" type="button" className="btn-ghost min-w-[3.25rem] px-2 py-1 font-mono text-[10px] tabular-nums" aria-label="Reset zoom to 100%" onClick={() => setZoom(1)}>
              {Math.round(zoom * 100)}%
            </button>
            <span id="spatial-crop-zoom-pct" className="sr-only">{Math.round(zoom * 100)}%</span>
            <button id="spatial-crop-zoom-in" type="button" className="btn-ghost px-2 py-1 font-mono text-xs" aria-label="Zoom in" disabled={zoom >= ZOOM_MAX} onClick={() => adjustZoom(ZOOM_STEP)}>
              +
            </button>
          </div>
          <div className="flex gap-2">
            <button id="spatial-crop-clear-btn" type="button" className="btn-ghost text-xs" onClick={() => onApply(null)}>
              Clear crop
            </button>
            <button id="spatial-crop-apply-btn" type="button" className="btn-primary text-xs" onClick={handleApply}>
              Apply crop
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
