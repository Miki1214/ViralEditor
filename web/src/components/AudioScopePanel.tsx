import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { loopSeamPreviewUrl, previewAudioUrl } from "../api/client";
import { TARGET_DURATION_PRESETS } from "../constants/durations";
import type { MusicBlock, WaveformPayload } from "../types";
import { MusicBlockCard, type PreviewMode } from "./MusicBlockCard";
import { ScopeCanvas, blockPixelRange, scopeWidth } from "./ScopeCanvas";
import { MusicDetailRack } from "./scope/MusicDetailRack";

interface AudioScopePanelProps {
  jobId: string;
  waveform: WaveformPayload;
  targetDurationS: number;
  useFullTrack: boolean;
  selectedBlockId: string | null;
  onTargetChange: (targetDurationS: number, useFullTrack: boolean) => void;
  onSelectBlock: (block: MusicBlock) => void;
  embedded?: boolean;
  switchingTarget?: boolean;
}

function TargetSwitchSpinner({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-monitor-muted/25 border-t-hook-gold ${className}`}
      role="status"
      aria-label="Switching target length"
    />
  );
}

function ChipSwitchOverlay({
  switching,
  children,
}: {
  switching: boolean;
  children: ReactNode;
}) {
  return (
    <span className="relative inline-flex items-center">
      {switching && (
        <span className="absolute inset-0 flex items-center justify-center">
          <TargetSwitchSpinner />
        </span>
      )}
      <span className={switching ? "invisible inline-flex items-center" : "inline-flex items-center"}>
        {children}
      </span>
    </span>
  );
}

function fallbackFullTrackBlock(waveform: WaveformPayload): MusicBlock {
  return {
    id: "block_full",
    start_s: 0,
    end_s: waveform.duration_s,
    duration_s: waveform.duration_s,
    score: 1,
    drop_count: waveform.transients.filter((t) => t.type === "drop").length,
    transient_count: waveform.transients.length,
    label: "Full track",
    reason: "Preview the full track",
    loop_quality: 0,
    phrase_bars: 0,
    section_label: null,
    key: waveform.key,
    is_repeated_section: false,
  };
}

function durationChipClass(
  active: boolean,
  unavailable: boolean,
  isBestLoop: boolean,
): string {
  if (unavailable) {
    return "cursor-not-allowed rounded border border-monitor-border/50 px-2.5 py-1 font-mono text-xs text-monitor-muted/40";
  }
  if (active) {
    return "rounded border border-hook-gold bg-hook-gold/15 px-2.5 py-1 font-mono text-xs text-hook-gold transition";
  }
  if (isBestLoop) {
    return "duration-chip-best-loop rounded border px-2.5 py-1 font-mono text-xs transition hover:border-hook-gold/30";
  }
  return "rounded border border-monitor-border px-2.5 py-1 font-mono text-xs text-monitor-muted transition hover:border-scope-dim";
}

function loopQualityLabel(pct: number): string {
  if (pct >= 78) return "seamless";
  if (pct >= 62) return "smooth";
  return "aligned";
}

export function AudioScopePanel({
  jobId,
  waveform,
  targetDurationS,
  useFullTrack,
  selectedBlockId,
  onTargetChange,
  onSelectBlock,
  embedded = false,
  switchingTarget = false,
}: AudioScopePanelProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const scopeScrollRef = useRef<HTMLDivElement>(null);
  const [playingBlockId, setPlayingBlockId] = useState<string | null>(null);
  const [playingMode, setPlayingMode] = useState<PreviewMode | null>(null);

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
    };
  }, []);

  const stopPreview = () => {
    audioRef.current?.pause();
    setPlayingBlockId(null);
    setPlayingMode(null);
  };

  useEffect(() => {
    if (!switchingTarget) return;
    stopPreview();
  }, [switchingTarget]);

  const handlePreview = (block: MusicBlock, mode: PreviewMode) => {
    if (playingBlockId === block.id && playingMode === mode) {
      stopPreview();
      return;
    }

    if (!audioRef.current) {
      audioRef.current = new Audio();
    }

    const audio = audioRef.current;
    audio.pause();
    audio.loop = true;
    audio.src =
      mode === "loop"
        ? loopSeamPreviewUrl(jobId, block.start_s, block.end_s)
        : previewAudioUrl(jobId, block.start_s, block.end_s);
    audio.currentTime = 0;
    void audio.play();
    setPlayingBlockId(block.id);
    setPlayingMode(mode);
  };

  const blocks =
    waveform.blocks.length > 0 ? waveform.blocks : [fallbackFullTrackBlock(waveform)];

  const scrollBlockIntoView = useCallback(
    (block: MusicBlock) => {
      const container = scopeScrollRef.current;
      if (!container || waveform.duration_s <= 0) return;

      const { startX, endX, canvasWidth } = blockPixelRange(
        waveform.duration_s,
        block.start_s,
        block.end_s,
      );
      const viewLeft = container.scrollLeft;
      const viewRight = viewLeft + container.clientWidth;
      const edgePadding = 32;

      if (startX >= viewLeft + edgePadding && endX <= viewRight - edgePadding) {
        return;
      }

      const blockCenter = (startX + endX) / 2;
      const maxScroll = Math.max(0, canvasWidth - container.clientWidth);
      const target = Math.max(
        0,
        Math.min(blockCenter - container.clientWidth / 2, maxScroll),
      );
      container.scrollTo({ left: target, behavior: "smooth" });
    },
    [waveform.duration_s],
  );

  useEffect(() => {
    if (!selectedBlockId) return;
    const block = blocks.find((entry) => entry.id === selectedBlockId);
    if (block) scrollBlockIntoView(block);
  }, [selectedBlockId, blocks, scrollBlockIntoView]);

  const trackShorterThanTarget = waveform.duration_s <= targetDurationS;
  const onlyFullTrack =
    blocks.length === 1 && blocks[0]?.id === "block_full";
  const targetMismatch =
    waveform.target_match_failed === true && !trackShorterThanTarget;
  const suggestedTarget =
    waveform.suggested_target_duration_s != null
      ? Math.round(waveform.suggested_target_duration_s)
      : null;

  const isPresetMatchable = (value: number): boolean => {
    if (waveform.duration_s <= value) {
      return false;
    }
    const matchable = waveform.matchable_target_durations_s;
    if (!matchable?.length) {
      return true;
    }
    return matchable.some((duration) => Math.round(duration) === value);
  };

  const loopQualityByPreset = useMemo(() => {
    const map = new Map<number, number>();
    for (const entry of waveform.target_loop_qualities ?? []) {
      map.set(Math.round(entry.target_duration_s), entry.loop_quality_pct);
    }
    return map;
  }, [waveform.target_loop_qualities]);

  const bestLoopPresets = useMemo(() => {
    const qualities = waveform.target_loop_qualities ?? [];
    if (qualities.length === 0) {
      return new Set<number>();
    }
    const maxPct = Math.max(...qualities.map((entry) => entry.loop_quality_pct));
    return new Set(
      qualities
        .filter((entry) => entry.loop_quality_pct === maxPct)
        .map((entry) => Math.round(entry.target_duration_s)),
    );
  }, [waveform.target_loop_qualities]);

  const tiedBestLoop = bestLoopPresets.size > 1;

  return (
    <section
      className={
        embedded
          ? "space-y-4 pt-4"
          : "panel space-y-4 p-5"
      }
    >
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Audio scope
          </h2>
          <p className="mt-1 font-mono text-sm text-scope-trace">
            {waveform.global_bpm.toFixed(1)} BPM · {waveform.duration_s.toFixed(1)}s track
            {waveform.key ? ` · ${waveform.key}` : ""}
            {waveform.beat_engine ? ` · ${waveform.beat_engine}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[10px] uppercase tracking-wider text-monitor-muted">
            Target short length
          </span>
          {TARGET_DURATION_PRESETS.map((preset) => {
            const matchable = isPresetMatchable(preset.value);
            const active = !useFullTrack && targetDurationS === preset.value;
            const switching = switchingTarget && active;
            const unavailable = !matchable && !active;
            const loopQualityPct = loopQualityByPreset.get(preset.value);
            const isBestLoop =
              bestLoopPresets.has(preset.value) && !active && matchable;
            const qualityTitle =
              loopQualityPct != null
                ? isBestLoop
                  ? tiedBestLoop
                    ? `Tied best loop — ${loopQualityPct}% ${loopQualityLabel(loopQualityPct)}`
                    : `Best seamless loop — ${loopQualityPct}% ${loopQualityLabel(loopQualityPct)}`
                  : active
                    ? `Selected · ${loopQualityPct}% ${loopQualityLabel(loopQualityPct)} loop`
                    : `${loopQualityPct}% ${loopQualityLabel(loopQualityPct)} loop`
                : unavailable
                  ? "No phrase-aligned loop at this length for this track"
                  : undefined;
            return (
            <button
              key={preset.value}
              type="button"
              disabled={unavailable || switchingTarget}
              title={qualityTitle}
              className={durationChipClass(active, unavailable, isBestLoop)}
              onClick={() => onTargetChange(preset.value, false)}
            >
              <ChipSwitchOverlay switching={switching}>
                <span>{preset.label}</span>
                {loopQualityPct != null && (
                  <span
                    className={`ml-1 text-[10px] ${
                      active
                        ? "text-hook-gold/75"
                        : isBestLoop
                          ? "text-monitor-muted/45"
                          : "text-monitor-muted/55"
                    }`}
                  >
                    {loopQualityPct}%
                  </span>
                )}
              </ChipSwitchOverlay>
            </button>
            );
          })}
          <button
            type="button"
            disabled={switchingTarget}
            className={`rounded border px-2.5 py-1 font-mono text-xs transition ${
              useFullTrack || trackShorterThanTarget
                ? "border-hook-gold bg-hook-gold/15 text-hook-gold"
                : "border-monitor-border text-monitor-muted hover:border-scope-dim"
            } ${switchingTarget ? "cursor-not-allowed" : ""}`}
            onClick={() => onTargetChange(waveform.duration_s, true)}
          >
            <ChipSwitchOverlay
              switching={switchingTarget && (useFullTrack || trackShorterThanTarget)}
            >
              <span>Full</span>
            </ChipSwitchOverlay>
          </button>
        </div>
      </div>

      <div className="space-y-1">
        {scopeWidth(waveform.duration_s) > 960 && (
          <p className="font-mono text-[10px] text-monitor-muted">
            Scroll horizontally to inspect the full track
          </p>
        )}
        <div ref={scopeScrollRef} className="space-y-2 overflow-x-auto pb-1">
          <ScopeCanvas
            durationS={waveform.duration_s}
            points={waveform.points}
            transients={waveform.transients}
            sections={waveform.sections}
            beats={waveform.beats ?? []}
            downbeats={waveform.downbeats}
            blocks={blocks}
            selectedBlockId={selectedBlockId}
            playingBlockId={playingBlockId}
          />
          <MusicDetailRack
            lanes={waveform.lanes ?? []}
            chroma={waveform.chroma ?? null}
            window={{ startS: 0, endS: waveform.duration_s }}
            viewWidth={scopeWidth(waveform.duration_s)}
          />
        </div>
      </div>

      <div className="space-y-2">
        {(trackShorterThanTarget || targetMismatch) && !switchingTarget && (
          <p className="text-sm text-monitor-muted">
            {trackShorterThanTarget
              ? "Track is shorter than the target — the full track will drive the render."
              : suggestedTarget != null
                ? `No phrase-aligned loop for ${targetDurationS}s — ${suggestedTarget}s is the closest match. Preview the full track below or switch length.`
                : "No phrase-aligned window matched this target — preview the full track below."}
          </p>
        )}
        <div className="flex items-center gap-2">
          {switchingTarget && <TargetSwitchSpinner />}
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            {switchingTarget
              ? "Updating blocks…"
              : onlyFullTrack
                ? "Track preview"
                : "Suggested blocks"}
          </p>
        </div>
        <div
          className={`space-y-2 ${
            switchingTarget ? "pointer-events-none opacity-45" : ""
          }`}
        >
          {blocks.map((block) => (
            <MusicBlockCard
              key={block.id}
              block={block}
              selected={block.id === selectedBlockId}
              playingMode={playingBlockId === block.id ? playingMode : null}
              onSelect={() => onSelectBlock(block)}
              onAudition={() => handlePreview(block, "audition")}
              onLoopPreview={() => handlePreview(block, "loop")}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
