import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { previewAudioUrl } from "../api/client";
import type { SlotRole, StoryboardPayload, StorySlot } from "../types";

interface StoryboardBlockPlayerProps {
  jobId: string;
  storyboard: StoryboardPayload;
  selectedSlotId: string | null;
  playheadS: number;
  onPlayheadChange: (seconds: number) => void;
  onSelectSlot?: (slotId: string) => void;
}

const SLOT_MARKER: Record<SlotRole, string> = {
  hook: "#F4C430",
  punch: "#38BDF8",
  clip: "#3DDC84",
};

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
}: StoryboardBlockPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [loopSlot, setLoopSlot] = useState(true);
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

  useEffect(() => {
    setPlaying(false);
    setReady(false);
    onPlayheadChange(0);
  }, [audioUrl, onPlayheadChange]);

  useEffect(() => {
    if (!loopSlot || !selectedSlot) return;
    const audio = audioRef.current;
    if (!audio) return;
    audio.currentTime = selectedSlot.out_start_s;
    onPlayheadChange(selectedSlot.out_start_s);
  }, [selectedSlot?.id, loopSlot, selectedSlot, onPlayheadChange]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onTimeUpdate = () => {
      const t = audio.currentTime;
      if (loopSlot && selectedSlot && t >= selectedSlot.out_end_s - 0.04) {
        audio.currentTime = selectedSlot.out_start_s;
        onPlayheadChange(selectedSlot.out_start_s);
        return;
      }
      onPlayheadChange(Math.min(t, blockDurationS));
    };

    const onEnded = () => setPlaying(false);
    const onLoaded = () => setReady(true);

    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("ended", onEnded);
    audio.addEventListener("loadedmetadata", onLoaded);
    return () => {
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("ended", onEnded);
      audio.removeEventListener("loadedmetadata", onLoaded);
    };
  }, [blockDurationS, loopSlot, selectedSlot, onPlayheadChange]);

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio || !ready) return;
    if (playing) {
      audio.pause();
      setPlaying(false);
      return;
    }
    if (loopSlot && selectedSlot && playheadS >= selectedSlot.out_end_s - 0.05) {
      audio.currentTime = selectedSlot.out_start_s;
      onPlayheadChange(selectedSlot.out_start_s);
    }
    void audio.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  };

  const seek = (timeS: number) => {
    const audio = audioRef.current;
    if (!audio) return;
    const clamped = Math.max(0, Math.min(timeS, blockDurationS));
    audio.currentTime = clamped;
    onPlayheadChange(clamped);
    const hit = slotAtTime(clamped);
    if (hit && hit.id !== selectedSlotId) {
      onSelectSlot?.(hit.id);
    }
  };

  const playSelectedSlot = () => {
    if (!selectedSlot) return;
    seek(selectedSlot.out_start_s);
    setLoopSlot(true);
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
          {orderedSlots.map((slot) => {
            const left = (slot.out_start_s / blockDurationS) * 100;
            const width = ((slot.out_end_s - slot.out_start_s) / blockDurationS) * 100;
            const selected = slot.id === selectedSlotId;
            return (
              <div
                key={slot.id}
                className="absolute inset-y-0 opacity-80"
                style={{
                  left: `${left}%`,
                  width: `${width}%`,
                  backgroundColor: selected
                    ? SLOT_MARKER[slot.role]
                    : `${SLOT_MARKER[slot.role]}55`,
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
          step={0.05}
          value={playheadS}
          disabled={!ready}
          onChange={(e) => seek(Number(e.target.value))}
          aria-label="Block audio scrubber"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn-ghost px-2.5 py-1.5 font-mono text-xs"
          disabled={!ready}
          onClick={togglePlay}
          aria-label={playing ? "Pause block audio" : "Play block audio"}
        >
          {playing ? "Pause" : "Play"}
        </button>
        {selectedSlot && (
          <button
            type="button"
            className="btn-ghost px-2.5 py-1.5 font-mono text-xs"
            disabled={!ready}
            onClick={playSelectedSlot}
          >
            Play slot
          </button>
        )}
        <label className="ml-auto flex items-center gap-2 font-mono text-[10px] text-monitor-muted">
          <input
            type="checkbox"
            className="accent-scope-trace"
            checked={loopSlot}
            onChange={(e) => setLoopSlot(e.target.checked)}
          />
          Loop selected slot
        </label>
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
          <span style={{ color: SLOT_MARKER[activeSlot.role] }}>
            {activeSlot.label} · {formatTime(activeSlot.out_end_s - activeSlot.out_start_s)}
          </span>
        ) : (
          <span>No slot</span>
        )}
        {selectedSlot && loopSlot && (
          <span className="text-scope-dim">
            looping {selectedSlot.label.toLowerCase()}
          </span>
        )}
      </div>
    </div>
  );
}
