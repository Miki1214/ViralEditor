import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { previewAudioUrl } from "../api/client";
import type { StoryboardPayload, StorySlot } from "../types";
import { subscribePlayhead } from "../utils/playheadBus";
import { slotColorForIndex } from "../utils/slotColors";

export type StoryboardLoopMode = "slot" | "block";

export type PlayheadChangeOptions = {
  /** When false, update storyboard UI only — skip App-level state (default true). */
  commit?: boolean;
};

export type BlockPlayheadChangeHandler = (
  seconds: number,
  options?: PlayheadChangeOptions,
) => void;

interface StoryboardBlockPlayerProps {
  jobId: string;
  storyboard: StoryboardPayload;
  selectedSlotId: string | null;
  playheadS: number;
  onPlayheadChange: BlockPlayheadChangeHandler;
  onSelectSlot?: (slotId: string) => void;
  /** Composed preview drives transport instead of block audio */
  compositePreviewActive?: boolean;
  compositePreviewPlaying?: boolean;
  onToggleCompositePreview?: () => void;
  onSeekCompositePreview?: (blockPlayheadS: number) => void;
  onPlayCompositePreview?: () => void;
  onLoopModeChange?: (mode: StoryboardLoopMode) => void;
  registerBlockSeek?: (handler: ((blockPlayheadS: number) => void) | null) => void;
  registerBlockPause?: (handler: (() => void) | null) => void;
  registerBlockPlaySlot?: (handler: ((slotId: string) => void) | null) => void;
  registerBlockSetLoopMode?: (handler: ((mode: StoryboardLoopMode) => void) | null) => void;
}

function formatTime(seconds: number): string {
  return `${Math.max(0, seconds).toFixed(1)}s`;
}

function applyPlayheadDom(
  timeS: number,
  durationS: number,
  slider: HTMLInputElement | null,
  marker: HTMLDivElement | null,
  timeEl: HTMLSpanElement | null,
): void {
  if (durationS <= 0) return;
  const clamped = Math.max(0, Math.min(timeS, durationS));
  if (slider) slider.value = String(clamped);
  if (marker) {
    marker.style.left = `${(clamped / durationS) * 100}%`;
  }
  if (timeEl) {
    timeEl.textContent = `${formatTime(clamped)} / ${formatTime(durationS)}`;
  }
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
  onLoopModeChange,
  registerBlockSeek,
  registerBlockPause,
  registerBlockPlaySlot,
  registerBlockSetLoopMode,
}: StoryboardBlockPlayerProps) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const sliderRef = useRef<HTMLInputElement>(null);
  const playheadMarkerRef = useRef<HTMLDivElement>(null);
  const timeDisplayRef = useRef<HTMLSpanElement>(null);
  const prevAudioTimeRef = useRef(0);
  const loopModeRef = useRef<StoryboardLoopMode>("block");
  const selectedSlotRef = useRef<StorySlot | null>(null);
  const onPlayheadChangeRef = useRef(onPlayheadChange);
  const blockDurationRef = useRef(0);
  const scrubbingRef = useRef(false);
  const pendingSlotIdRef = useRef<string | null>(null);
  const lastAppCommitRef = useRef(0);
  const scrubValueRef = useRef(0);
  const activeSlotRef = useRef<HTMLSpanElement>(null);
  const orderedSlotsRef = useRef<StorySlot[]>([]);
  const [playing, setPlaying] = useState(false);
  const [loopMode, setLoopMode] = useState<StoryboardLoopMode>("block");
  const [ready, setReady] = useState(false);
  const [scrubbing, setScrubbing] = useState(false);

  const blockDurationS = storyboard.total_duration_s;
  const audioUrl = previewAudioUrl(jobId, storyboard.music_start_s, storyboard.music_end_s);

  const orderedSlots = useMemo(
    () => [...storyboard.slots].sort((a, b) => a.order - b.order),
    [storyboard.slots],
  );
  orderedSlotsRef.current = orderedSlots;

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

  const updatePlayheadDom = useCallback((timeS: number) => {
    applyPlayheadDom(
      timeS,
      blockDurationRef.current,
      sliderRef.current,
      playheadMarkerRef.current,
      timeDisplayRef.current,
    );
  }, []);

  const updateActiveSlotLabel = useCallback((timeS: number) => {
    const el = activeSlotRef.current;
    if (!el) return;
    const hit = orderedSlotsRef.current.find(
      (slot) => timeS >= slot.out_start_s - 0.001 && timeS < slot.out_end_s - 0.001,
    );
    if (hit) {
      el.textContent = `${hit.label} · ${formatTime(hit.out_end_s - hit.out_start_s)}`;
      const index = orderedSlotsRef.current.findIndex((slot) => slot.id === hit.id);
      if (index >= 0) {
        el.style.color = slotColorForIndex(index).stroke;
      }
    } else {
      el.textContent = "No slot";
      el.style.color = "";
    }
  }, []);

  useEffect(() => {
    return subscribePlayhead((timeS) => {
      if (scrubbingRef.current) return;
      updatePlayheadDom(timeS);
      updateActiveSlotLabel(timeS);
    });
  }, [updatePlayheadDom, updateActiveSlotLabel]);

  useEffect(() => {
    if (scrubbingRef.current) return;
    updatePlayheadDom(playheadS);
  }, [playheadS, blockDurationS, updatePlayheadDom]);

  const setLoopModeAndNotify = useCallback(
    (mode: StoryboardLoopMode) => {
      loopModeRef.current = mode;
      setLoopMode(mode);
      onLoopModeChange?.(mode);
    },
    [onLoopModeChange],
  );

  const publishPlayhead = useCallback(
    (timeS: number, options?: PlayheadChangeOptions) => {
      onPlayheadChangeRef.current(timeS, options);
    },
    [],
  );

  const syncPlayheadFromAudio = useCallback((audio: HTMLAudioElement) => {
    const t = audio.currentTime;
    const mode = loopModeRef.current;
    const slot = selectedSlotRef.current;
    const blockDuration = blockDurationRef.current;

    const emit = (next: number, commit: boolean) => {
      publishPlayhead(next, { commit });
      if (commit) {
        lastAppCommitRef.current = performance.now();
      }
    };

    if (mode === "slot" && slot && t >= slot.out_end_s - 0.04) {
      audio.currentTime = slot.out_start_s;
      emit(slot.out_start_s, true);
      prevAudioTimeRef.current = slot.out_start_s;
      return;
    }
    if (mode === "block") {
      if (t >= blockDuration - 0.04) {
        audio.currentTime = 0;
        emit(0, true);
        prevAudioTimeRef.current = 0;
        return;
      }
      const now = performance.now();
      const commit = now - lastAppCommitRef.current >= 150;
      emit(t, commit);
      prevAudioTimeRef.current = t;
      return;
    }
    const clamped = Math.min(t, blockDuration);
    const now = performance.now();
    emit(clamped, now - lastAppCommitRef.current >= 150);
    prevAudioTimeRef.current = clamped;
  }, [publishPlayhead]);

  useEffect(() => {
    if (!compositePreviewActive) return;
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    setPlaying(false);
  }, [compositePreviewActive, audioUrl]);

  useEffect(() => {
    setPlaying(false);
    setReady(false);
    setScrubbing(false);
    scrubbingRef.current = false;
    prevAudioTimeRef.current = 0;
    publishPlayhead(0, { commit: true });
  }, [audioUrl, publishPlayhead]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.loop = false;
  }, [loopMode, audioUrl]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;

    const onEnded = () => {
      if (loopModeRef.current === "block") {
        audio.currentTime = 0;
        onPlayheadChangeRef.current(0, { commit: true });
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

  const pause = useCallback(() => {
    if (compositePreviewActive) {
      if (compositePreviewPlaying) {
        onToggleCompositePreview?.();
      }
      return;
    }
    const audio = audioRef.current;
    if (!audio) return;
    audio.pause();
    syncPlayheadFromAudio(audio);
    setPlaying(false);
  }, [compositePreviewActive, compositePreviewPlaying, onToggleCompositePreview, syncPlayheadFromAudio]);

  const playSlot = useCallback(
    (slot: StorySlot, options?: { toggleIfPlaying?: boolean }) => {
      const toggleIfPlaying = options?.toggleIfPlaying ?? false;
      if (
        toggleIfPlaying &&
        transportPlaying &&
        loopMode === "slot" &&
        selectedSlot?.id === slot.id
      ) {
        pause();
        return;
      }
      setLoopModeAndNotify("slot");
      if (compositePreviewActive) {
        onSeekCompositePreview?.(slot.out_start_s);
        publishPlayhead(slot.out_start_s, { commit: true });
        onPlayCompositePreview?.();
        return;
      }
      const audio = audioRef.current;
      if (!audio || !ready) return;
      audio.currentTime = slot.out_start_s;
      publishPlayhead(slot.out_start_s, { commit: true });
      void audio.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
    },
    [
      transportPlaying,
      loopMode,
      selectedSlot?.id,
      pause,
      setLoopModeAndNotify,
      compositePreviewActive,
      onSeekCompositePreview,
      publishPlayhead,
      onPlayCompositePreview,
      ready,
    ],
  );

  const playTrack = () => {
    if (transportPlaying && loopMode === "block") {
      pause();
      return;
    }
    setLoopModeAndNotify("block");
    if (compositePreviewActive) {
      onSeekCompositePreview?.(0);
      publishPlayhead(0, { commit: true });
      onPlayCompositePreview?.();
      return;
    }
    const audio = audioRef.current;
    if (!audio || !ready) return;
    audio.currentTime = 0;
    publishPlayhead(0, { commit: true });
    void audio.play().then(() => setPlaying(true)).catch(() => setPlaying(false));
  };

  const playSelectedSlot = () => {
    if (!selectedSlot) return;
    playSlot(selectedSlot, { toggleIfPlaying: true });
  };

  const seek = useCallback(
    (timeS: number, options?: { commit?: boolean; selectSlot?: boolean }) => {
      const commit = options?.commit !== false;
      const selectSlot = options?.selectSlot !== false;
      const clamped = Math.max(0, Math.min(timeS, blockDurationS));
      updatePlayheadDom(clamped);

      if (compositePreviewActive) {
        if (commit) {
          onSeekCompositePreview?.(clamped);
        }
        publishPlayhead(clamped, { commit });
        prevAudioTimeRef.current = clamped;
        if (selectSlot) {
          const hit = slotAtTime(clamped);
          if (hit && hit.id !== selectedSlotId) {
            onSelectSlot?.(hit.id);
          }
        }
        return;
      }
      const audio = audioRef.current;
      if (audio) {
        audio.currentTime = clamped;
      }
      publishPlayhead(clamped, { commit });
      prevAudioTimeRef.current = clamped;
      if (selectSlot) {
        const hit = slotAtTime(clamped);
        if (hit && hit.id !== selectedSlotId) {
          onSelectSlot?.(hit.id);
        }
      }
    },
    [
      blockDurationS,
      compositePreviewActive,
      onSeekCompositePreview,
      publishPlayhead,
      slotAtTime,
      selectedSlotId,
      onSelectSlot,
    ],
  );

  const finishScrub = useCallback(() => {
    if (!scrubbingRef.current) return;
    scrubbingRef.current = false;
    setScrubbing(false);
    const timeS = scrubValueRef.current;
    updatePlayheadDom(timeS);
    if (pendingSlotIdRef.current) {
      onSelectSlot?.(pendingSlotIdRef.current);
      pendingSlotIdRef.current = null;
    }
    seek(timeS, { commit: true, selectSlot: false });
  }, [onSelectSlot, seek]);

  useEffect(() => {
    if (!scrubbing) return;
    const onPointerUp = () => finishScrub();
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
    return () => {
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerUp);
    };
  }, [scrubbing, finishScrub]);

  const handleScrubInput = useCallback(
    (timeS: number) => {
      const clamped = Math.max(0, Math.min(timeS, blockDurationS));
      scrubValueRef.current = clamped;
      scrubbingRef.current = true;
      updatePlayheadDom(clamped);
      updateActiveSlotLabel(clamped);
      const hit = slotAtTime(clamped);
      if (hit && hit.id !== selectedSlotId) {
        pendingSlotIdRef.current = hit.id;
      }
      seek(clamped, { commit: false, selectSlot: false });
    },
    [blockDurationS, seek, slotAtTime, selectedSlotId, updatePlayheadDom, updateActiveSlotLabel],
  );

  const beginScrub = useCallback(() => {
    if (scrubbingRef.current) return;
    scrubbingRef.current = true;
    setScrubbing(true);
    pendingSlotIdRef.current = null;
    scrubValueRef.current = Number(sliderRef.current?.value ?? playheadS);
  }, [playheadS]);

  useEffect(() => {
    registerBlockSeek?.((timeS) => seek(timeS));
    return () => registerBlockSeek?.(null);
  }, [registerBlockSeek, seek]);

  useEffect(() => {
    registerBlockPause?.(() => pause());
    return () => registerBlockPause?.(null);
  }, [registerBlockPause, pause]);

  useEffect(() => {
    registerBlockPlaySlot?.((slotId) => {
      const slot = orderedSlots.find((item) => item.id === slotId);
      if (slot) {
        playSlot(slot, { toggleIfPlaying: false });
      }
    });
    return () => registerBlockPlaySlot?.(null);
  }, [registerBlockPlaySlot, orderedSlots, playSlot]);

  useEffect(() => {
    registerBlockSetLoopMode?.((mode) => setLoopModeAndNotify(mode));
    return () => registerBlockSetLoopMode?.(null);
  }, [registerBlockSetLoopMode, setLoopModeAndNotify]);

  const displayActiveSlot = activeSlot;

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
            ref={playheadMarkerRef}
            className="absolute inset-y-0 w-0.5 bg-monitor-text shadow-[0_0_6px_rgba(232,234,237,0.8)]"
            style={{ left: "0%" }}
          />
        </div>
        <input
          key={audioUrl}
          ref={sliderRef}
          type="range"
          className="field-range relative z-[1]"
          min={0}
          max={blockDurationS}
          step={0.001}
          defaultValue={0}
          disabled={!transportReady}
          onPointerDown={beginScrub}
          onChange={(e) => handleScrubInput(Number(e.target.value))}
          aria-label="Block audio scrubber"
        />
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          className="btn-ghost px-2.5 py-1.5 font-mono text-xs"
          disabled={!transportReady}
          onClick={playTrack}
          aria-label={
            transportPlaying && loopMode === "block" ? "Pause track" : "Play whole track"
          }
        >
          {transportPlaying && loopMode === "block" ? "Pause" : "Play track"}
        </button>
        {selectedSlot && (
          <button
            type="button"
            className="btn-ghost px-2.5 py-1.5 font-mono text-xs"
            disabled={!transportReady}
            onClick={playSelectedSlot}
            aria-label={
              transportPlaying && loopMode === "slot" ? "Pause slot" : "Play selected slot"
            }
          >
            {transportPlaying && loopMode === "slot" ? "Pause" : "Play slot"}
          </button>
        )}
      </div>

      <p className="font-mono text-[10px] text-monitor-muted">
        Highlight follows the selected slot&apos;s music window
        {onSelectSlot ? " · click waveform to switch slots" : ""}
      </p>

      <div className="flex flex-wrap items-center justify-between gap-2 font-mono text-[10px] text-monitor-muted">
        <span ref={timeDisplayRef}>
          {formatTime(playheadS)} / {formatTime(blockDurationS)}
        </span>
        {displayActiveSlot ? (
          <span ref={activeSlotRef} style={{ color: activeSlotColor }}>
            {displayActiveSlot.label} ·{" "}
            {formatTime(displayActiveSlot.out_end_s - displayActiveSlot.out_start_s)}
          </span>
        ) : (
          <span ref={activeSlotRef}>No slot</span>
        )}
        {transportPlaying && loopMode === "slot" && selectedSlot ? (
          <span className="text-scope-dim">
            looping {selectedSlot.label.toLowerCase()}
          </span>
        ) : transportPlaying && loopMode === "block" ? (
          <span className="text-scope-dim">looping whole track</span>
        ) : null}
      </div>
    </div>
  );
}
