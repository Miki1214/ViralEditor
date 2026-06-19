interface PhonePreviewProps {
  hookText: string;
  emphasisWords: string;
  fillColor: string;
  emphasisColor: string;
  fontFamily: string;
  safePaddingPct: number;
  videoPreviewUrl: string | null;
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
}: PhonePreviewProps) {
  return (
    <div className="relative w-[min(100%,280px)]">
      <div
        className="relative aspect-[9/16] w-full overflow-hidden rounded-[1.75rem] shadow-phone"
        style={{ background: "#0a0b0d" }}
      >
        {videoPreviewUrl ? (
          <video
            src={videoPreviewUrl}
            className="absolute inset-0 h-full w-full object-cover opacity-70"
            muted
            playsInline
            autoPlay
            loop
          />
        ) : (
          <div className="absolute inset-0 bg-gradient-to-b from-monitor-surface to-monitor-bg" />
        )}

        {/* Safe zone grid — signature element */}
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

        <div className="pointer-events-none absolute inset-x-0 top-0 h-16 bg-gradient-to-b from-black/50 to-transparent" />
      </div>
      <p className="mt-3 text-center font-mono text-[10px] text-monitor-muted">
        1080 × 1920 · teaser window overlay
      </p>
    </div>
  );
}
