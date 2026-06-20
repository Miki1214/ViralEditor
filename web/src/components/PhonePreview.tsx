import { useEffect, useMemo, useRef, useState } from "react";
import type { StoryboardPayload, StorySlot } from "../types";
import {
  blockPlayheadToCompositeVideoTime,
  compositeVideoTimeToBlockPlayhead,
} from "../utils/compositePlayhead";
import type { StoryboardLoopMode, BlockPlayheadChangeHandler } from "./StoryboardBlockPlayer";

export interface PreviewTransportRestore {
  playheadS: number;
  playing: boolean;
  loopMode: StoryboardLoopMode;
  selectedSlotId: string | null;
}

interface PhonePreviewProps {
  hookText: string;
  emphasisWords: string;
  fillColor: string;
  emphasisColor: string;
  fontFamily: string;
  safePaddingPct: number;
  videoPreviewUrl: string | null;
  /** Server-side or probe error message for composited preview */
  loadErrorMessage?: string | null;
  /** When true, hook title overlay is baked into the composite video */
  compositeMode?: boolean;
  storyboard?: StoryboardPayload | null;
  loopMode?: StoryboardLoopMode;
  selectedSlotId?: string | null;
  onBlockPlayheadChange?: BlockPlayheadChangeHandler;
  onPreviewPlayingChange?: (playing: boolean) => void;
  previewRestoreRef?: React.MutableRefObject<PreviewTransportRestore | null>;
  onApplyPreviewRestore?: (restore: PreviewTransportRestore) => void;
  registerPreviewToggle?: (handler: (() => void) | null) => void;
  registerPreviewSeek?: (handler: ((videoTimeS: number) => void) | null) => void;
  registerPreviewPlay?: (handler: (() => void) | null) => void;
}

function renderHookLine(
  text: string,
  emphasisWords: string,
  fillColor: string,
  emphasisColor: string,
) {
  const tokens = emphasisWords
    .split(",")
    .map((w) => w.trim().toLowerCase())
    .filter(Boolean);

  return text.split(/(\s+)/).map((part, index) => {
    const normalized = part.trim().toLowerCase();
    const emphasized = normalized.length > 0 && tokens.includes(normalized);
    return (
      <span
        key={`${part}-${index}`}
        style={{ color: emphasized ? emphasisColor : fillColor }}
      >
        {part}
      </span>
    );
  });
}

export function PhonePreview({
  hookText,
  emphasisWords,
  fillColor,
  emphasisColor,
  fontFamily,
  safePaddingPct,
  videoPreviewUrl,
  loadErrorMessage = null,
  compositeMode = false,
  storyboard = null,
  loopMode = "block",
  selectedSlotId = null,
  onBlockPlayheadChange,
  onPreviewPlayingChange,
  previewRestoreRef,
  onApplyPreviewRestore,
  registerPreviewToggle,
  registerPreviewSeek,
  registerPreviewPlay,
}: PhonePreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const storyboardRef = useRef(storyboard);
  const loopModeRef = useRef(loopMode);
  const loopSlotRef = useRef<StorySlot | null>(null);
  const onPlayheadRef = useRef(onBlockPlayheadChange);
  const lastPreviewCommitRef = useRef(0);
  const ignorePauseRef = useRef(false);
  const transportReadyRef = useRef(false);
  const [loadFailed, setLoadFailed] = useState(false);

  const selectedSlot = useMemo(() => {
    if (!storyboard || !selectedSlotId) return null;
    return storyboard.slots.find((slot) => slot.id === selectedSlotId) ?? null;
  }, [storyboard, selectedSlotId]);

  storyboardRef.current = storyboard;
  loopModeRef.current = loopMode;
  loopSlotRef.current = selectedSlot;
  onPlayheadRef.current = onBlockPlayheadChange;

  useEffect(() => {
    setLoadFailed(false);
    transportReadyRef.current = false;
    ignorePauseRef.current = previewRestoreRef?.current != null;
  }, [videoPreviewUrl, previewRestoreRef, loadErrorMessage]);

  const showPreviewError = loadFailed || Boolean(loadErrorMessage);
  const previewErrorText =
    loadErrorMessage ??
    "Preview failed to load — use Refresh preview after assigning clips";

  useEffect(() => {
    if (!compositeMode || !videoPreviewUrl) return;
    const video = videoRef.current;
    if (!video) return;

    const restorePosition = () => {
      const sb = storyboardRef.current;
      if (!sb) return;

      const restore = previewRestoreRef?.current;
      if (restore) {
        onApplyPreviewRestore?.(restore);
        video.currentTime = blockPlayheadToCompositeVideoTime(restore.playheadS, sb);
        previewRestoreRef.current = null;
        ignorePauseRef.current = false;
        if (restore.playing) {
          void video.play().catch(() => undefined);
        } else {
          onPreviewPlayingChange?.(false);
        }
      } else {
        video.currentTime = 0;
        onPlayheadRef.current?.(0, { commit: true });
      }
      transportReadyRef.current = true;
    };

    const onLoaded = () => restorePosition();

    video.addEventListener("loadedmetadata", onLoaded);
    if (video.readyState >= 1) {
      restorePosition();
    }
    return () => video.removeEventListener("loadedmetadata", onLoaded);
  }, [
    compositeMode,
    videoPreviewUrl,
    previewRestoreRef,
    onApplyPreviewRestore,
    onPreviewPlayingChange,
  ]);

  useEffect(() => {
    registerPreviewToggle?.(() => {
      const video = videoRef.current;
      if (!video) return;
      if (video.paused) {
        void video.play().catch(() => undefined);
      } else {
        video.pause();
      }
    });
    return () => registerPreviewToggle?.(null);
  }, [registerPreviewToggle, videoPreviewUrl]);

  useEffect(() => {
    registerPreviewSeek?.((videoTimeS: number) => {
      const video = videoRef.current;
      if (!video) return;
      video.currentTime = videoTimeS;
    });
    return () => registerPreviewSeek?.(null);
  }, [registerPreviewSeek, videoPreviewUrl]);

  useEffect(() => {
    registerPreviewPlay?.(() => {
      const video = videoRef.current;
      if (!video) return;
      void video.play().catch(() => undefined);
    });
    return () => registerPreviewPlay?.(null);
  }, [registerPreviewPlay, videoPreviewUrl]);

  useEffect(() => {
    if (!compositeMode || !videoPreviewUrl) return;
    const video = videoRef.current;
    if (!video) return;

    const emitPlayhead = (forceCommit = false) => {
      if (!transportReadyRef.current) return;
      const sb = storyboardRef.current;
      const onChange = onPlayheadRef.current;
      if (!sb || !onChange) return;

      const mode = loopModeRef.current;
      const slot = loopSlotRef.current;
      let blockPlayhead = compositeVideoTimeToBlockPlayhead(video.currentTime, sb);

      if (mode === "slot" && slot && blockPlayhead >= slot.out_end_s - 0.04) {
        const seekTo = blockPlayheadToCompositeVideoTime(slot.out_start_s, sb);
        video.currentTime = seekTo;
        onChange(slot.out_start_s, { commit: true });
        lastPreviewCommitRef.current = performance.now();
        return;
      }

      const now = performance.now();
      const commit = forceCommit || now - lastPreviewCommitRef.current >= 150;
      onChange(blockPlayhead, { commit });
      if (commit) {
        lastPreviewCommitRef.current = now;
      }
    };

    const onSeeked = () => emitPlayhead(true);

    let frameId = 0;
    const tick = () => {
      if (!video.paused) {
        emitPlayhead();
      }
      frameId = requestAnimationFrame(tick);
    };
    frameId = requestAnimationFrame(tick);

    video.addEventListener("seeked", onSeeked);
    return () => {
      cancelAnimationFrame(frameId);
      video.removeEventListener("seeked", onSeeked);
    };
  }, [compositeMode, videoPreviewUrl, loopMode, selectedSlotId]);

  const videoLoop = compositeMode && loopMode === "block";

  return (
    <div className="relative w-[min(100%,280px)]">
      <div
        className="relative aspect-[9/16] w-full overflow-hidden rounded-[1.75rem] shadow-phone"
        style={{ background: "#0a0b0d" }}
      >
        {videoPreviewUrl ? (
          <>
            <video
              ref={videoRef}
              key={videoPreviewUrl}
              src={videoPreviewUrl}
              className={`monitor-video absolute inset-0 h-full w-full object-cover ${compositeMode ? "" : "opacity-70"}`}
              playsInline
              loop={videoLoop}
              controls={compositeMode}
              onPlay={() => onPreviewPlayingChange?.(true)}
              onPause={() => {
                if (ignorePauseRef.current) return;
                onPreviewPlayingChange?.(false);
              }}
              onError={() => setLoadFailed(true)}
            />
            {showPreviewError && (
              <div className="absolute inset-0 flex items-center justify-center bg-monitor-bg/90 px-4 text-center font-mono text-[10px] text-hook-gold">
                {previewErrorText}
              </div>
            )}
          </>
        ) : (
          <div className="absolute inset-0 bg-gradient-to-b from-monitor-surface to-monitor-bg" />
        )}

        {!compositeMode && (
          <>
            <div
              className="pointer-events-none absolute border border-dashed border-scope-trace/35"
              style={{
                inset: `${safePaddingPct}%`,
              }}
            >
              <span className="absolute left-1 top-1 font-mono text-[8px] uppercase tracking-widest text-scope-trace/70">
                safe
              </span>
            </div>

            <div className="absolute inset-x-0 bottom-[18%] px-6 text-center">
              <div
                className="mx-auto inline-block rounded-2xl px-4 py-3"
                style={{
                  background: "rgba(0,0,0,0.85)",
                  fontFamily,
                  fontWeight: 800,
                  fontSize: "1.05rem",
                  lineHeight: 1.25,
                  maxWidth: `${100 - safePaddingPct * 2}%`,
                }}
              >
                {renderHookLine(hookText, emphasisWords, fillColor, emphasisColor)}
              </div>
            </div>
          </>
        )}

        <div className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-gradient-to-b from-black/50 to-transparent" />
      </div>
      <p className="mt-3 text-center font-mono text-[10px] text-monitor-muted">
        {compositeMode
          ? storyboard?.teaser.enabled
            ? "Composited preview · hook inversion + spatial FX"
            : "Composited preview · spatial FX + transitions"
          : "1080 × 1920 · assign slots to preview"}
      </p>
    </div>
  );
}
