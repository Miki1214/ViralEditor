import { useEffect, useMemo, useRef, useState } from "react";
import type { CaptionChunkPayload } from "../types";

interface CaptionWordTimelineProps {
  slotLabel: string;
  durationS: number;
  chunks: CaptionChunkPayload[];
  editable?: boolean;
  hasAsrTiming?: boolean;
  onWordTextChange?: (wordIndex: number, newText: string) => void;
}

export function CaptionWordTimeline({
  slotLabel,
  durationS,
  chunks,
  editable = false,
  hasAsrTiming = false,
  onWordTextChange,
}: CaptionWordTimelineProps) {
  const trackRef = useRef<HTMLDivElement>(null);
  const editInputRef = useRef<HTMLInputElement>(null);
  const [dragWordKey, setDragWordKey] = useState<string | null>(null);
  const [editingWordIndex, setEditingWordIndex] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");

  const words = useMemo(
    () =>
      chunks.flatMap((chunk, chunkIndex) =>
        chunk.words.map((word, wordIndex) => ({
          key: `${chunkIndex}-${wordIndex}`,
          flatIndex: 0,
          ...word,
        })),
      ).map((word, flatIndex) => ({ ...word, flatIndex })),
    [chunks],
  );

  useEffect(() => {
    if (editingWordIndex !== null) {
      editInputRef.current?.focus();
      editInputRef.current?.select();
    }
  }, [editingWordIndex]);

  const commitEdit = () => {
    if (editingWordIndex === null || !onWordTextChange) {
      setEditingWordIndex(null);
      return;
    }
    const trimmed = editValue.trim();
    const current = words[editingWordIndex];
    if (trimmed && trimmed !== current.text) {
      onWordTextChange(editingWordIndex, trimmed);
    }
    setEditingWordIndex(null);
  };

  const startEdit = (flatIndex: number) => {
    if (!editable || !onWordTextChange) return;
    setEditingWordIndex(flatIndex);
    setEditValue(words[flatIndex].text);
  };

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
          const isEditing = editingWordIndex === word.flatIndex;
          return (
            <button
              key={word.key}
              type="button"
              title={`${word.text} (${word.start_s.toFixed(2)}s–${word.end_s.toFixed(2)}s)`}
              className={`absolute top-1 bottom-1 truncate rounded px-1 font-mono text-[9px] ${
                isEditing
                  ? "bg-scope-trace text-monitor-bg z-10"
                  : dragWordKey === word.key
                    ? "bg-scope-trace text-monitor-bg"
                    : word.emphasis
                      ? "bg-hook-gold/30 text-hook-gold"
                      : "bg-scope-trace/20 text-scope-trace"
              } ${editable ? "cursor-text" : ""}`}
              style={{ left: `${leftPct}%`, width: `${widthPct}%` }}
              onMouseDown={() => {
                if (!editable) setDragWordKey(word.key);
              }}
              onMouseUp={() => {
                if (!editable) setDragWordKey(null);
              }}
              onDoubleClick={() => startEdit(word.flatIndex)}
            >
              {isEditing ? (
                <input
                  ref={editInputRef}
                  className="w-full min-w-0 bg-transparent text-inherit outline-none"
                  value={editValue}
                  onChange={(e) => setEditValue(e.target.value)}
                  onBlur={() => commitEdit()}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      commitEdit();
                    }
                    if (e.key === "Escape") {
                      setEditingWordIndex(null);
                    }
                  }}
                  onClick={(e) => e.stopPropagation()}
                  onMouseDown={(e) => e.stopPropagation()}
                />
              ) : (
                word.text
              )}
            </button>
          );
        })}
      </div>
      <p className="text-[10px] text-monitor-muted">
        {hasAsrTiming
          ? "ASR word timings — double-click a word to fix typos"
          : "Drag handles coming soon — timings are auto-split evenly within each phrase chunk."}
      </p>
    </div>
  );
}
