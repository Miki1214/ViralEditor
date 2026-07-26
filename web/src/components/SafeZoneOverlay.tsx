interface SafeZoneOverlayProps {
  visible: boolean;
}

/** Approximate TikTok / Reels UI safe zones over 9:16 preview. */
export function SafeZoneOverlay({ visible }: SafeZoneOverlayProps) {
  if (!visible) return null;

  return (
    <div
      className="pointer-events-none absolute inset-0 z-20"
      aria-hidden
    >
      {/* Top status / creator bar */}
      <div className="absolute left-0 right-0 top-0 h-[8%] border-b border-dashed border-white/25 bg-white/5" />
      {/* Right action rail (like, comment, share) */}
      <div className="absolute bottom-[18%] right-0 w-[14%] top-[22%] border-l border-dashed border-white/25 bg-white/5" />
      {/* Bottom caption / username bar */}
      <div className="absolute bottom-0 left-0 right-[16%] h-[16%] border-t border-dashed border-white/25 bg-white/5" />
      <p className="absolute bottom-2 left-2 font-mono text-[8px] uppercase tracking-wider text-white/60">
        Safe zone
      </p>
    </div>
  );
}
