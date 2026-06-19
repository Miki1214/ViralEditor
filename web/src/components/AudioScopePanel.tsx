import { useEffect, useRef, useState } from "react";
import { loopSeamPreviewUrl, previewAudioUrl } from "../api/client";
import type { MusicBlock, WaveformPayload } from "../types";
import { MusicBlockCard, type PreviewMode } from "./MusicBlockCard";
import { ScopeCanvas } from "./ScopeCanvas";

const TARGET_PRESETS = [
  { label: "15s", value: 15 },
  { label: "30s", value: 30 },
  { label: "45s", value: 45 },
  { label: "60s", value: 60 },
] as const;

interface AudioScopePanelProps {
  jobId: string;
  waveform: WaveformPayload;
  targetDurationS: number;
  useFullTrack: boolean;
  selectedBlockId: string | null;
  onTargetChange: (targetDurationS: number, useFullTrack: boolean) => void;
  onSelectBlock: (block: MusicBlock) => void;
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

export function AudioScopePanel({
  jobId,
  waveform,
  targetDurationS,
  useFullTrack,
  selectedBlockId,
  onTargetChange,
  onSelectBlock,
}: AudioScopePanelProps) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
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
    audio.loop = mode === "loop";
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
  const trackShorterThanTarget = waveform.duration_s <= targetDurationS;
  const onlyFullTrack =
    blocks.length === 1 && blocks[0]?.id === "block_full";

  return (
    <section className="panel space-y-4 p-5">
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
          {TARGET_PRESETS.map((preset) => (
            <button
              key={preset.value}
              type="button"
              disabled={waveform.duration_s <= preset.value}
              className={`rounded border px-2.5 py-1 font-mono text-xs transition ${
                !useFullTrack && targetDurationS === preset.value
                  ? "border-hook-gold bg-hook-gold/15 text-hook-gold"
                  : waveform.duration_s <= preset.value
                    ? "cursor-not-allowed border-monitor-border/50 text-monitor-muted/40"
                    : "border-monitor-border text-monitor-muted hover:border-scope-dim"
              }`}
              onClick={() => onTargetChange(preset.value, false)}
            >
              {preset.label}
            </button>
          ))}
          <button
            type="button"
            className={`rounded border px-2.5 py-1 font-mono text-xs transition ${
              useFullTrack || trackShorterThanTarget
                ? "border-hook-gold bg-hook-gold/15 text-hook-gold"
                : "border-monitor-border text-monitor-muted hover:border-scope-dim"
            }`}
            onClick={() => onTargetChange(waveform.duration_s, true)}
          >
            Full
          </button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <ScopeCanvas
          durationS={waveform.duration_s}
          points={waveform.points}
          transients={waveform.transients}
          sections={waveform.sections}
          downbeats={waveform.downbeats}
          blocks={blocks}
          selectedBlockId={selectedBlockId}
          playingBlockId={playingBlockId}
        />
      </div>

      <div className="space-y-2">
        {(trackShorterThanTarget || onlyFullTrack) && (
          <p className="text-sm text-monitor-muted">
            {trackShorterThanTarget
              ? "Track is shorter than the target — the full track will drive the render."
              : "No shorter phrase-aligned window matched this target — preview the full track below."}
          </p>
        )}
        <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
          {onlyFullTrack ? "Track preview" : "Suggested blocks"}
        </p>
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
    </section>
  );
}
