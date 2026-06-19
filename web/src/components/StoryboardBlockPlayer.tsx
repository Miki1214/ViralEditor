import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { previewAudioUrl } from "../api/client";
import type { StoryboardPayload, StorySlot } from "../types";
import { slotColorForIndex } from "../utils/slotColors";

type LoopMode = "slot" | "block";

interface StoryboardBlockPlayerProps {
  jobId: string;
  storyboard: StoryboardPayload;
  selectedSlotId: string | null;
  playheadS: number;
  onPlayheadChange: (seconds: number) => void;
  onSelectSlot?: (slotId: string) => void;
  /** Composed preview drives transport instead of block audio */
  compositePreviewActive?: boolean;
  compositePreviewPlaying?: boolean;
  onToggleCompositePreview?: () => void;
  onSeekCompositePreview?: (blockPlayheadS: number) => void;
  onPlayCompositePreview?: () => void;
}

function formatTime(seconds: number): string {
  return `${Math.max(0, seconds).toFixed(1)}s`;
}

export function StoryboardBlockPlayer({
  jobId,
  storyboard,
  selectedSlotId,
  playheadS,
  onPlayheadChange,
  onSelectSlot,
  compositePreviewActive = false,
  compositePreviewPlaying = false,
  onToggleCompositePreview,
  onSeekCompositePreview,
  onPlayCompositePreview,
}: StoryboardBlockPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const prevAudioTimeRef = useRef(0);
  const loopModeRef = useRef<LoopMode>("slot");
  const selectedSlotRef = useRef<StorySlot | null>(null);
  const onPlayheadChangeRef = useRef(onPlayheadChange);
  const blockDurationRef = useRef(0);
  const [playing, setPlaying] = useState(false);
  const [loopMode, setLoopMode] = useState<LoopMode>("slot");
  const [ready, setReady] = useState(false);

  const blockDurationS = storyboard.total_duration_s;
  const audioUrl = previewAudioUrl(jobId, storyboard.music_start_s, storyboard.music_end_s);

  const orderedSlots = useMemo(
    () => [...storyboard.slots].sort((a, b) => a.order - b.order),
    [storyboard.slots],
  );

  const selectedSlot = useMemo(
    () => orderedSlots.find((slot) => slot.id === selectedSlotId) ?? null,
    [orderedSlots, selectedSlotId],
  );

  const slotAtTime = useCallback(
    (timeS: number): StorySlot | null =>
      orderedSlots.find(
        (slot) => timeS >= slot.out_start_s - 0.001 && timeS < slot.out_end_s - 0.001,
      ) ?? null,
    [orderedSlots],
  );

  const activeSlot = slotAtTime(playheadS);
  const activeSlotIndex = activeSlot
    ? orderedSlots.findIndex((slot) => slot.id === activeSlot.id)
    : -1;
  const activeSlotColor =
    activeSlotIndex >= 0 ? slotColorForIndex(activeSlotIndex).stroke : undefined;

  loopModeRef.current = loopMode;
  selectedSlotRef.current = selectedSlot;
  onPlayheadChangeRef.current = onPlayheadChange;
  blockDurationRef.current = blockDurationS;

  const syncPlayheadFromAudio = useCallback((audio: HTMLAudioElement) => {
    const t = audio.currentTime;
    const mode = loopModeRef.current;
    const slot = selectedSlotRef.current;
    const blockDuration = blockDurationRef.current;

    if (mode === "slot" && slot && t >= slot.out_end_s - 0.04) {
      audio.currentTime = slot.out_start_s;
      onPlayheadChangeRef.current(slot.out_start_s);
      prevAudioTimeRef.current = slot.out_start_s;
      return;
    }
    if (mode === "block") {
      if (t >= blockDuration - 0.04) {
        audio.currentTime = 0;
        onPlayheadChangeRef.current(0);
        prevAudioTimeRef.current = 0;
        return;
      }
      onPlayheadChangeRef.current(t);
      prevAudioTimeRef.current = t;
      return;
    }
    const clamped = Math.min(t, blockDuration);
    onPlayheadChangeRef.current(clamped);
    prevAudioTimeRef.current = clamped;
  }, []);

  useEffect(() => {
    if (!compositePreviewActive) return;
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    setPlaying(false);
  }, [compositePreviewActive, audioUrl]);

  useEffect(() => {
    if (loopMode === "slot" && !selectedSlot) {
      setLoopMode("block");
    }
  }, [loopMode, selectedSlot]);

  useEffect(() => {
    setPlaying(false);
    setReady(false);
    prevAudioTimeRef.current = 0;
    onPlayheadChange(0);
  }, [audioUrl, onPlayheadChange]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.loop = false;
  }, [loopMode, audioUrl]);

  useEffect(() => {
    if (loopMode !== "slot" || !selectedSlot) return;
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = selectedSlot.out_start_s;
    onPlayheadChange(selectedSlot.out_start_s);
  }, [selectedSlot?.id, loopMode, selectedSlot, onPlayheadChange]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onEnded = () => {
      if (loopModeRef.current === "block") {
        audio.currentTime = 0;
        onPlayheadChangeRef.current(0);
        prevAudioTimeRef.current = 0;
        void audio.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
        return;
      }
      setPlaying(false);
    };
    const onLoaded = () => setReady(true);

    audio.addEventListener("ended", onEnded);
    audio.addEventListener("loadedmetadata", onLoaded);
    return () => {
      audio.removeEventListener("ended", onEnded);
      audio.removeEventListener("loadedmetadata", onLoaded);
    };
  }, [audioUrl]);

  useEffect(() => {
    if (!playing) return;
    const audio = audioRef.current;
    if (!audio) return;

    let frameId = 0;
    const tick = () => {
      if (!audio.paused) {
        syncPlayheadFromAudio(audio);
      }
      frameId = requestAnimationFrame(tick);
    };
    frameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frameId);
  }, [playing, syncPlayheadFromAudio, audioUrl]);

  const transportReady = compositePreviewActive || ready;
  const transportPlaying = compositePreviewActive ? compositePreviewPlaying : playing;

  const togglePlay = () => {
    if (compositePreviewActive) {
      onToggleCompositePreview?.();
      return;
    }
    const audio = audioRef.current;
    if (!audio || !ready) return;
    if (playing) {
      audio.pause();
      syncPlayheadFromAudio(audio);
      setPlaying(false);
      return;
    }
    if (loopMode === "slot" && selectedSlot && playheadS >= selectedSlot.out_end_s - 0.05) {
      audio.currentTime = selectedSlot.out_start_s;
      onPlayheadChange(selectedSlot.out_start_s);
    } else if (loopMode === "block" && playheadS >= blockDurationS - 0.05) {
      audio.currentTime = 0;
      onPlayheadChange(0);
    }
    void audio.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  };

  const seek = (timeS: number) => {
    const clamped = Math.max(0, Math.min(timeS, blockDurationS));
    if (compositePreviewActive) {
      onSeekCompositePreview?.(clamped);
      onPlayheadChange(clamped);
      prevAudioTimeRef.current = clamped;
      const hit = slotAtTime(clamped);
      if (hit && hit.id !== selectedSlotId) {
        onSelectSlot?.(hit.id);
      }
      return;
    }
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = clamped;
    onPlayheadChange(clamped);
    prevAudioTimeRef.current = clamped;
    const hit = slotAtTime(clamped);
    if (hit && hit.id !== selectedSlotId) {
      onSelectSlot?.(hit.id);
    }
  };

  const playSelectedSlot = () => {
    if (!selectedSlot) return;
    seek(selectedSlot.out_start_s);
    setLoopMode("slot");
    if (compositePreviewActive) {
      onPlayCompositePreview?.();
      return;
    }
    const audio = audioRef.current;
    if (!audio || !ready) return;
    void audio.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  };

  const playheadPct =
    blockDurationS > 0 ? Math.max(0, Math.min(100, (playheadS / blockDurationS) * 100)) : 0;

  return (
    <div className="space-y-2 rounded border border-monitor-border bg-monitor-bg/50 p-3">
      <audio ref={audioRef} src={audioUrl} preload="metadata" />

      <div className="relative pt-1">
        <div
          className="pointer-events-none absolute inset-x-0 top-1 h-1.5 overflow-hidden rounded-full bg-[#2a3038]"
          aria-hidden
        >
          {orderedSlots.map((slot, index) => {
            const left = (slot.out_start_s / blockDurationS) * 100;
            const width = ((slot.out_end_s - slot.out_start_s) / blockDurationS) * 100;
            const selected = slot.id === selectedSlotId;
            const color = slotColorForIndex(index);
            return (
              <div
                key={slot.id}
                className="absolute inset-y-0 opacity-80"
                style={{
                  left: `${left}%`,
                  width: `${width}%`,
                  backgroundColor: selected ? color.stroke : `${color.stroke}66`,
                }}
              />
            );
          })}
          <div
            className="absolute inset-y-0 w-0.5 bg-monitor-text shadow-[0_0_6px_rgba(232,234,237,0.8)]"
            style={{ left: `${playheadPct}%` }}
          />
        </div>
        <input
          type="range"
          className="field-range relative z-[1]"
          min={0}
          max={blockDurationS}
          step={0.001}
          value={playheadS}
          disabled={!transportReady}
          onChange={(e) => seek(Number(e.target.value))}
          aria-label="Block audio scrubber"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn-ghost px-2.5 py-1.5 font-mono text-xs"
          disabled={!transportReady}
          onClick={togglePlay}
          aria-label={transportPlaying ? "Pause preview" : "Play preview"}
        >
          {transportPlaying ? "Pause" : "Play"}
        </button>
        {selectedSlot && (
          <button
            type="button"
            className="btn-ghost px-2.5 py-1.5 font-mono text-xs"
            disabled={!transportReady}
            onClick={playSelectedSlot}
          >
            Play slot
          </button>
        )}
        <fieldset className="ml-auto flex items-center gap-3 border-0 p-0">
          <legend className="sr-only">Loop mode</legend>
          <label className="flex cursor-pointer items-center gap-1.5 font-mono text-[10px] text-monitor-muted">
            <input
              type="radio"
              name="storyboard-loop-mode"
              className="accent-scope-trace"
              checked={loopMode === "slot"}
              disabled={!selectedSlot}
              onChange={() => setLoopMode("slot")}
            />
            Loop slot
          </label>
          <label className="flex cursor-pointer items-center gap-1.5 font-mono text-[10px] text-monitor-muted">
            <input
              type="radio"
              name="storyboard-loop-mode"
              className="accent-scope-trace"
              checked={loopMode === "block"}
              onChange={() => setLoopMode("block")}
            />
            Loop track
          </label>
        </fieldset>
      </div>

      <p className="font-mono text-[10px] text-monitor-muted">
        Highlight follows the selected slot&apos;s music window
        {onSelectSlot ? " · click waveform to switch slots" : ""}
      </p>

      <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[10px] text-monitor-muted">
        <span>
          {formatTime(playheadS)} / {formatTime(blockDurationS)}
        </span>
        {activeSlot ? (
          <span style={{ color: activeSlotColor }}>
            {activeSlot.label} · {formatTime(activeSlot.out_end_s - activeSlot.out_start_s)}
          </span>
        ) : (
          <span>No slot</span>
        )}
        {loopMode === "slot" && selectedSlot ? (
          <span className="text-scope-dim">
            looping {selectedSlot.label.toLowerCase()}
          </span>
        ) : loopMode === "block" ? (
          <span className="text-scope-dim">looping whole track</span>
        ) : null}
      </div>
    </div>
  );
}
