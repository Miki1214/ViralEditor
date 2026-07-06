import { useMemo, useRef, useState } from "react";
import type { CaptionChunkPayload } from "../types";

interface CaptionWordTimelineProps {
  slotLabel: string;
  durationS: number;
  chunks: CaptionChunkPayload[];
}

export function CaptionWordTimeline({
  slotLabel,
  durationS,
  chunks,
}: CaptionWordTimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const [dragWordKey, setDragWordKey] = useState<string | null>(null);

  const words = useMemo(
    () =>
      chunks.flatMap((chunk, chunkIndex) =>
        chunk.words.map((word, wordIndex) => ({
          key: `${chunkIndex}-${wordIndex}`,
          ...word,
        })),
      ),
    [chunks],
  );

  return (
    <div className="rounded border border-monitor-border bg-monitor-bg/40 p-3 space-y-2">
      <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-monitor-muted">
        Word timing · {slotLabel}
      </p>
      <div
        ref={trackRef}
        className="relative h-10 rounded bg-monitor-bg border border-monitor-border overflow-hidden"
      >
        {words.map((word) => {
          const leftPct = (word.start_s / durationS) * 100;
          const widthPct = Math.max(((word.end_s - word.start_s) / durationS) * 100, 2);
          return (
            <button
              key={word.key}
              type="button"
              title={`${word.text} (${word.start_s.toFixed(2)}s–${word.end_s.toFixed(2)}s)`}
              className={`absolute top-1 bottom-1 truncate rounded px-1 font-mono text-[9px] ${
                dragWordKey === word.key
                  ? "bg-scope-trace text-monitor-bg"
                  : word.emphasis
                    ? "bg-hook-gold/30 text-hook-gold"
                    : "bg-scope-trace/20 text-scope-trace"
              }`}
              style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
              onMouseDown={() => setDragWordKey(word.key)}
              onMouseUp={() => setDragWordKey(null)}
            >
              {word.text}
            </button>
          );
        })}
      </div>
      <p className="text-[10px] text-monitor-muted">
        Drag handles coming soon — timings are auto-split evenly within each phrase chunk.
      </p>
    </div>
  );
}
