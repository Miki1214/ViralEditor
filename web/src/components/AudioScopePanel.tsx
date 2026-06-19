import { useEffect, useRef, useState } from "react";
import { previewAudioUrl } from "../api/client";
import type { MusicBlock, WaveformPayload } from "../types";
import { MusicBlockCard } from "./MusicBlockCard";
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

  useEffect(() => {
    return () => {
      audioRef.current?.pause();
    };
  }, []);

  const handleListen = (block: MusicBlock) => {
    if (playingBlockId === block.id) {
      audioRef.current?.pause();
      setPlayingBlockId(null);
      return;
    }

    if (!audioRef.current) {
      audioRef.current = new Audio();
    }

    const audio = audioRef.current;
    audio.loop = false;
    audio.pause();
    audio.src = previewAudioUrl(jobId, block.start_s, block.end_s);
    audio.currentTime = 0;
    void audio.play();
    setPlayingBlockId(block.id);
  };

  const showBlockPicker = !waveform.blocks.some((block) => block.id === "block_full");

  return (
    <section className="panel space-y-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Audio scope
          </h2>
          <p className="mt-1 font-mono text-sm text-scope-trace">
            {waveform.global_bpm.toFixed(1)} BPM · {waveform.duration_s.toFixed(1)}s track
          </p>
        </div>
        {showBlockPicker && (
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-[10px] uppercase tracking-wider text-monitor-muted">
              Target short length
            </span>
            {TARGET_PRESETS.map((preset) => (
              <button
                key={preset.value}
                type="button"
                className={`rounded border px-2.5 py-1 font-mono text-xs transition ${
                  !useFullTrack && targetDurationS === preset.value
                    ? "border-hook-gold bg-hook-gold/15 text-hook-gold"
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
                useFullTrack
                  ? "border-hook-gold bg-hook-gold/15 text-hook-gold"
                  : "border-monitor-border text-monitor-muted hover:border-scope-dim"
              }`}
              onClick={() => onTargetChange(waveform.duration_s, true)}
            >
              Full
            </button>
          </div>
        )}
      </div>

      <div className="overflow-x-auto">
        <ScopeCanvas
          durationS={waveform.duration_s}
          points={waveform.points}
          transients={waveform.transients}
          blocks={waveform.blocks}
          selectedBlockId={selectedBlockId}
          playingBlockId={playingBlockId}
        />
      </div>

      {showBlockPicker ? (
        <div className="space-y-2">
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Suggested blocks
          </p>
          {waveform.blocks.map((block) => (
            <MusicBlockCard
              key={block.id}
              block={block}
              selected={block.id === selectedBlockId}
              playing={block.id === playingBlockId}
              onSelect={() => onSelectBlock(block)}
              onListen={() => handleListen(block)}
            />
          ))}
        </div>
      ) : (
        <p className="text-sm text-monitor-muted">
          Track is already shorter than the target — the full track will drive the render.
        </p>
      )}
    </section>
  );
}
