import type { MusicBlock } from "../types";

function formatRange(startS: number, endS: number): string {
  const fmt = (value: number) => {
    const minutes = Math.floor(value / 60);
    const seconds = Math.floor(value % 60);
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  };
  return `${fmt(startS)}–${fmt(endS)}`;
}

interface MusicBlockCardProps {
  block: MusicBlock;
  selected: boolean;
  playing: boolean;
  onSelect: () => void;
  onListen: () => void;
}

export function MusicBlockCard({
  block,
  selected,
  playing,
  onSelect,
  onListen,
}: MusicBlockCardProps) {
  return (
    <div
      className={`rounded border px-3 py-2 transition ${
        selected
          ? "border-hook-gold/70 bg-hook-gold/10 shadow-[0_0_0_1px_rgba(244,196,48,0.25)]"
          : "border-monitor-border bg-monitor-bg hover:border-monitor-muted"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          className="min-w-0 flex-1 text-left"
          onClick={onSelect}
        >
          <p className="font-mono text-xs text-hook-gold">
            {block.label} · {formatRange(block.start_s, block.end_s)}
          </p>
          <p className="mt-0.5 text-sm text-monitor-text">
            {block.drop_count} drop{block.drop_count === 1 ? "" : "s"} ·{" "}
            {block.transient_count} hits
          </p>
          <p className="mt-1 text-xs text-monitor-muted">{block.reason}</p>
        </button>
        <button
          type="button"
          className="btn-ghost shrink-0 font-mono text-xs"
          onClick={onListen}
          aria-pressed={playing}
        >
          {playing ? "■ Stop" : "▶ Audition"}
        </button>
      </div>
    </div>
  );
}
