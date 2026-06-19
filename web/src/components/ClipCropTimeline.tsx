import { useCallback, useEffect, useRef, useState } from "react";

interface ClipCropTimelineProps {
  videoUrl: string;
  durationS: number;
  cropStartS: number;
  cropEndS: number;
  onCropChange: (startS: number, endS: number) => void;
}

const TRACE = "#3DDC84";
const DIM = "rgba(61,220,132,0.25)";
const HANDLE = "#3DDC84";

export function ClipCropTimeline({
  videoUrl,
  durationS,
  cropStartS,
  cropEndS,
  onCropChange,
}: ClipCropTimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<"start" | "end" | null>(null);

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
    if (!dragging) return;

    const onMove = (event: PointerEvent) => {
      const t = timeFromClientX(event.clientX);
      if (dragging === "start") {
        const { s, e } = clampCrop(t, cropEndS);
        onCropChange(s, e);
      } else {
        const { s, e } = clampCrop(cropStartS, t);
        onCropChange(s, e);
      }
    };

    const onUp = () => setDragging(null);
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
  }, [dragging, cropStartS, cropEndS, clampCrop, onCropChange, timeFromClientX]);

  const startPct = durationS > 0 ? (cropStartS / durationS) * 100 : 0;
  const endPct = durationS > 0 ? (cropEndS / durationS) * 100 : 100;

  return (
    <div className="space-y-2">
      <video
        src={videoUrl}
        className="max-h-28 w-full rounded border border-monitor-border bg-black object-contain"
        muted
        playsInline
        controls
      />
      <div
        ref={trackRef}
        className="relative h-8 cursor-crosshair rounded border border-monitor-border bg-monitor-bg"
        aria-label="Crop range"
      >
        <div className="absolute inset-y-0 left-0 bg-black/40" style={{ width: `${startPct}%` }} />
        <div
          className="absolute inset-y-0 right-0 bg-black/40"
          style={{ width: `${100 - endPct}%` }}
        />
        <div
          className="absolute inset-y-0 border-y-2"
          style={{
            left: `${startPct}%`,
            width: `${endPct - startPct}%`,
            borderColor: TRACE,
            backgroundColor: DIM,
          }}
        />
        <button
          type="button"
          className="absolute top-0 h-full w-2 -translate-x-1/2 rounded-sm"
          style={{ left: `${startPct}%`, backgroundColor: HANDLE }}
          onPointerDown={(e) => {
            e.preventDefault();
            setDragging("start");
          }}
          aria-label="Crop in"
        />
        <button
          type="button"
          className="absolute top-0 h-full w-2 -translate-x-1/2 rounded-sm"
          style={{ left: `${endPct}%`, backgroundColor: HANDLE }}
          onPointerDown={(e) => {
            e.preventDefault();
            setDragging("end");
          }}
          aria-label="Crop out"
        />
      </div>
      <p className="font-mono text-[11px] text-monitor-muted">
        {cropStartS.toFixed(2)}s → {cropEndS.toFixed(2)}s ({(cropEndS - cropStartS).toFixed(2)}s)
      </p>
    </div>
  );
}
