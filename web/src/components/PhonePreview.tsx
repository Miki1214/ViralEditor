import { useEffect, useRef, useState } from "react";
import type { StoryboardPayload } from "../types";
import { compositeVideoTimeToBlockPlayhead } from "../utils/compositePlayhead";

interface PhonePreviewProps {
  hookText: string;
  emphasisWords: string;
  fillColor: string;
  emphasisColor: string;
  fontFamily: string;
  safePaddingPct: number;
  videoPreviewUrl: string | null;
  /** When true, hook title overlay is baked into the composite video */
  compositeMode?: boolean;
  storyboard?: StoryboardPayload | null;
  onBlockPlayheadChange?: (seconds: number) => void;
  onPreviewPlayingChange?: (playing: boolean) => void;
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
  compositeMode = false,
  storyboard = null,
  onBlockPlayheadChange,
  onPreviewPlayingChange,
  registerPreviewToggle,
  registerPreviewSeek,
  registerPreviewPlay,
}: PhonePreviewProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const storyboardRef = useRef(storyboard);
  const onPlayheadRef = useRef(onBlockPlayheadChange);
  const [loadFailed, setLoadFailed] = useState(false);

  storyboardRef.current = storyboard;
  onPlayheadRef.current = onBlockPlayheadChange;

  useEffect(() => {
    setLoadFailed(false);
  }, [videoPreviewUrl]);

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

    const emitPlayhead = () => {
      const sb = storyboardRef.current;
      const onChange = onPlayheadRef.current;
      if (!sb || !onChange) return;
      onChange(compositeVideoTimeToBlockPlayhead(video.currentTime, sb));
    };

    let frameId = 0;
    const tick = () => {
      if (!video.paused) {
        emitPlayhead();
      }
      frameId = requestAnimationFrame(tick);
    };
    frameId = requestAnimationFrame(tick);

    video.addEventListener("seeked", emitPlayhead);
    return () => {
      cancelAnimationFrame(frameId);
      video.removeEventListener("seeked", emitPlayhead);
    };
  }, [compositeMode, videoPreviewUrl]);

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
              autoPlay
              loop
              controls={compositeMode}
              onPlay={() => onPreviewPlayingChange?.(true)}
              onPause={() => onPreviewPlayingChange?.(false)}
              onError={() => setLoadFailed(true)}
            />
            {loadFailed && (
              <div className="absolute inset-0 flex items-center justify-center bg-monitor-bg/90 px-4 text-center font-mono text-[10px] text-hook-gold">
                Preview failed to load — use Refresh preview after assigning clips
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
          ? "Composited preview · music + speed ramp + transitions"
          : "1080 × 1920 · assign slots to preview"}
      </p>
    </div>
  );
}
