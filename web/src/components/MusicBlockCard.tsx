import type { MusicBlock } from "../types";

function formatRange(startS: number, endS: number): string {
  const fmt = (value: number) => {
    const minutes = Math.floor(value / 60);
    const seconds = Math.floor(value % 60);
    return `${minutes}:${seconds.toString().padStart(2, "0")}`;
  };
  return `${fmt(startS)}–${fmt(endS)}`;
}

function loopQualityLabel(quality: number): string {
  if (quality >= 0.78) return "Seamless";
  if (quality >= 0.62) return "Smooth";
  if (quality >= 0.4) return "Aligned";
  return "Fair";
}

export type PreviewMode = "audition" | "loop";

interface MusicBlockCardProps {
  block: MusicBlock;
  selected: boolean;
  playingMode: PreviewMode | null;
  onSelect: () => void;
  onAudition: () => void;
  onLoopPreview: () => void;
}

export function MusicBlockCard({
  block,
  selected,
  playingMode,
  onSelect,
  onAudition,
  onLoopPreview,
}: MusicBlockCardProps) {
  const qualityPct = Math.round(block.loop_quality * 100);
  const auditionPlaying = playingMode === "audition";
  const loopPlaying = playingMode === "loop";

  return (
    <div
      id={`music-block-card-${block.id}`}
      className={`rounded border px-3 py-2 transition ${
        selected
          ? "border-hook-gold/70 bg-hook-gold/10 shadow-[0_0_0_1px_rgba(244,196,48,0.25)]"
          : "border-monitor-border bg-monitor-bg hover:border-monitor-muted"
      }`}
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <button
          id={`music-block-card-select-${block.id}`}
          type="button"
          className="min-w-0 flex-1 text-left"
          onClick={onSelect}
        >
          <p id={`music-block-card-label-${block.id}`} className="font-mono text-xs text-hook-gold">
            {block.label} · {formatRange(block.start_s, block.end_s)}
          </p>
          <p id={`music-block-card-info-${block.id}`} className="mt-0.5 text-sm text-monitor-text">
            {block.drop_count} drop{block.drop_count === 1 ? "" : "s"} ·{" "}
            {block.transient_count} hits
            {block.phrase_bars > 0 ? ` · ${block.phrase_bars}-bar phrase` : ""}
            {block.section_label ? ` · ${block.section_label}` : ""}
            {block.key ? ` · ${block.key}` : ""}
            {block.expected_slot_count != null && (
              <span id={`music-block-card-slot-badge-${block.id}`} className="ml-1 font-mono text-[10px] text-monitor-muted/70">
                · {block.expected_slot_count} slot{block.expected_slot_count !== 1 ? "s" : ""}
              </span>
            )}
          </p>
          <div className="mt-2 flex items-center gap-2">
            <span id={`music-block-card-loop-label-${block.id}`} className="font-mono text-[10px] uppercase tracking-wider text-monitor-muted">
              Loop
            </span>
            <div id={`music-block-card-loop-bar-${block.id}`} className="h-1.5 flex-1 overflow-hidden rounded bg-monitor-border">
              <div
                id={`music-block-card-loop-fill-${block.id}`}
                className="h-full rounded bg-scope-trace transition-all"
                style={{ width: `${qualityPct}%` }}
              />
            </div>
            <span id={`music-block-card-loop-pct-${block.id}`} className="font-mono text-[10px] text-monitor-muted">
              {loopQualityLabel(block.loop_quality)} {qualityPct}%
            </span>
          </div>
          <p id={`music-block-card-reason-${block.id}`} className="mt-1 text-xs text-monitor-muted">{block.reason}</p>
        </button>
        <div id={`music-block-card-play-btns-${block.id}`} className="flex shrink-0 flex-col items-stretch gap-1">
          <button
            id={`music-block-card-audition-${block.id}`}
            type="button"
            className="btn-ghost font-mono text-xs"
            onClick={onAudition}
            aria-pressed={auditionPlaying}
          >
            {auditionPlaying ? "■ Stop" : "▶ Audition"}
          </button>
          <button
            id={`music-block-card-loop-preview-${block.id}`}
            type="button"
            className="btn-ghost font-mono text-[10px] text-monitor-muted"
            onClick={onLoopPreview}
            aria-pressed={loopPlaying}
          >
            {loopPlaying ? "■ Stop loop" : "↻ Loop preview"}
          </button>
        </div>
      </div>
    </div>
  );
}
