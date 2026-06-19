import { useCallback, useEffect, useRef, useState } from "react";
import type { JobSummary, MusicBlock, PipelineEvent, StageInfo, StoryboardPayload, WaveformPayload } from "./types";
import {
  assignSlotClip,
  clearSlotClip,
  compositePreviewUrl,
  createDraftJob,
  fetchHealth,
  fetchJobs,
  fetchStages,
  fetchStoryboard,
  fetchWaveform,
  patchStoryboard,
  subscribeJobEvents,
  updateMusicSelection,
  updateSlotCrop,
  updateSlotTransform,
} from "./api/client";
import { DEFAULT_HOOK_FONT } from "./constants/fonts";
import { AudioScopePanel } from "./components/AudioScopePanel";
import { ConfirmDialog } from "./components/ConfirmDialog";
import { blockPlayheadToCompositeVideoTime } from "./utils/compositePlayhead";
import { HookOverlayPanel } from "./components/HookOverlayPanel";
import type { FormState } from "./components/JobForm";
import { JobForm } from "./components/JobForm";
import { OutputPanel } from "./components/OutputPanel";
import { PhonePreview } from "./components/PhonePreview";
import { StageTelemetry } from "./components/StageTelemetry";
import { StoryboardPanel } from "./components/StoryboardPanel";

const initialForm: FormState = {
  hookText: "I built this in 30 days",
  emphasisWords: "30, days",
  fillColor: "#FFFFFF",
  emphasisColor: "#FFD700",
  fontFamily: DEFAULT_HOOK_FONT,
  safePaddingPct: 10,
  targetDurationS: 10,
  useFullTrack: false,
};

export default function App() {
  const [form, setForm] = useState<FormState>(initialForm);
  const [stages, setStages] = useState<StageInfo[]>([]);
  const [events, setEvents] = useState<PipelineEvent[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [jobStatus, setJobStatus] = useState<JobSummary["status"] | null>(null);
  const [jobArtifacts, setJobArtifacts] = useState<string[]>([]);
  const [hasOutput, setHasOutput] = useState(false);
  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [ffmpegOk, setFfmpegOk] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [audioName, setAudioName] = useState<string | null>(null);
  const [waveform, setWaveform] = useState<WaveformPayload | null>(null);
  const [selectedBlockId, setSelectedBlockId] = useState<string | null>(null);
  const [musicStartS, setMusicStartS] = useState<number | null>(null);
  const [musicEndS, setMusicEndS] = useState<number | null>(null);
  const [storyboard, setStoryboard] = useState<StoryboardPayload | null>(null);
  const [selectedSlotId, setSelectedSlotId] = useState<string | null>(null);
  const [storyboardSaving, setStoryboardSaving] = useState(false);
  const [previewVersion, setPreviewVersion] = useState(0);
  const [previewReady, setPreviewReady] = useState(false);
  const [blockPlayheadS, setBlockPlayheadS] = useState(0);
  const [compositePreviewPlaying, setCompositePreviewPlaying] = useState(false);
  const togglePreviewRef = useRef<(() => void) | null>(null);
  const seekPreviewRef = useRef<((videoTimeS: number) => void) | null>(null);
  const playPreviewRef = useRef<(() => void) | null>(null);

  const registerPreviewToggle = useCallback((handler: (() => void) | null) => {
    togglePreviewRef.current = handler;
  }, []);
  const registerPreviewSeek = useCallback((handler: ((videoTimeS: number) => void) | null) => {
    seekPreviewRef.current = handler;
  }, []);
  const registerPreviewPlay = useCallback((handler: (() => void) | null) => {
    playPreviewRef.current = handler;
  }, []);
  const toggleCompositePreview = useCallback(() => {
    togglePreviewRef.current?.();
  }, []);
  const seekCompositeFromBlock = useCallback(
    (blockPlayheadS: number) => {
      if (!storyboard) return;
      seekPreviewRef.current?.(
        blockPlayheadToCompositeVideoTime(blockPlayheadS, storyboard),
      );
    },
    [storyboard],
  );
  const playCompositePreview = useCallback(() => {
    playPreviewRef.current?.();
  }, []);
  const [regeneratePrompt, setRegeneratePrompt] = useState<{
    targetDurationS: number;
    useFullTrack: boolean;
  } | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [targetSuggestionPrompt, setTargetSuggestionPrompt] = useState<{
    requested: number;
    suggested: number;
  } | null>(null);
  const [dismissedTargetSuggestions, setDismissedTargetSuggestions] = useState<Set<string>>(
    () => new Set(),
  );

  const patchForm = useCallback((partial: Partial<FormState>) => {
    setForm((prev) => ({ ...prev, ...partial }));
  }, []);

  const loadHealth = () => {
    fetchHealth()
      .then((h) => {
        setApiOnline(true);
        setFfmpegOk(h.ffmpeg_available);
      })
      .catch(() => {
        setApiOnline(false);
        setFfmpegOk(null);
      });
  };

  useEffect(() => {
    loadHealth();
    fetchStages().then(setStages).catch(() => undefined);
  }, []);

  useEffect(() => {
    if (
      !waveform?.target_match_failed ||
      waveform.suggested_target_duration_s == null ||
      !activeJobId ||
      form.useFullTrack
    ) {
      return;
    }
    const suggested = Math.round(waveform.suggested_target_duration_s);
    if (suggested === form.targetDurationS) {
      return;
    }
    const key = `${activeJobId}:${form.targetDurationS}:${suggested}`;
    if (dismissedTargetSuggestions.has(key)) {
      return;
    }
    setTargetSuggestionPrompt({
      requested: form.targetDurationS,
      suggested,
    });
  }, [
    waveform,
    activeJobId,
    form.targetDurationS,
    form.useFullTrack,
    dismissedTargetSuggestions,
  ]);

  const renderBlockedReason = (() => {
    if (apiOnline === false) {
      return "API offline — run: python -m viral_editor serve";
    }
    if (ffmpegOk === false) {
      return "FFmpeg not found on PATH — install FFmpeg, then restart the API.";
    }
    return null;
  })();

  const loadScope = (jobId: string) => {
    fetchWaveform(jobId)
      .then((payload) => {
        setWaveform(payload);
        setSelectedBlockId(payload.selected_block_id);
        const selected = payload.blocks.find((block) => block.id === payload.selected_block_id);
        if (selected) {
          setMusicStartS(selected.start_s);
          setMusicEndS(selected.end_s);
        }
      })
      .catch(() => {
        window.setTimeout(() => {
          fetchWaveform(jobId)
            .then((payload) => {
              setWaveform(payload);
              setSelectedBlockId(payload.selected_block_id);
            })
            .catch(() => undefined);
        }, 500);
      });
  };

  const loadStoryboard = (jobId: string) => {
    fetchStoryboard(jobId)
      .then((payload) => {
        setStoryboard(payload);
        setPreviewReady(payload.preview_ready);
        setSelectedSlotId((current) => current ?? payload.slots[0]?.id ?? null);
      })
      .catch(() => setStoryboard(null));
  };

  const handleAudioSelected = async (file: File) => {
    setError(null);
    setAnalyzing(true);
    setAudioName(file.name);
    setWaveform(null);
    setStoryboard(null);
    setEvents([]);
    setPreviewReady(false);
    setPreviewVersion(0);
    setDismissedTargetSuggestions(new Set());
    setTargetSuggestionPrompt(null);

    try {
      const { id } = await createDraftJob({
        audio: file,
        hookText: form.hookText,
        emphasisWords: form.emphasisWords,
        fillColor: form.fillColor,
        emphasisColor: form.emphasisColor,
        fontFamily: form.fontFamily,
        safePaddingPct: form.safePaddingPct,
        targetDurationS: form.targetDurationS,
        useFullTrack: form.useFullTrack,
      });

      setActiveJobId(id);
      setJobStatus("running");

      subscribeJobEvents(
        id,
        (event) => {
          setEvents((prev) => [...prev, event]);
          if (event.stage === "audio" && event.action === "complete") {
            loadScope(id);
            loadStoryboard(id);
          }
        },
        () => {
          setAnalyzing(false);
          fetchJobs()
            .then((list) => {
              const job = list.find((j) => j.id === id);
              if (job) {
                setJobStatus(job.status);
                setJobArtifacts(job.artifacts);
              }
            })
            .catch(() => undefined);
          loadScope(id);
          loadStoryboard(id);
        },
        (streamError) => {
          setAnalyzing(false);
          setError(streamError.message);
          setJobStatus("failed");
        },
      );
    } catch (err) {
      setAnalyzing(false);
      setError(err instanceof Error ? err.message : "Audio analysis failed");
    }
  };

  const handleTargetChange = async (targetDurationS: number, useFullTrack: boolean) => {
    if (!activeJobId) return;
    patchForm({ targetDurationS, useFullTrack });
    setRegenerating(true);
    try {
      await updateMusicSelection(activeJobId, {
        target_duration_s: targetDurationS,
        use_full_track: useFullTrack,
      });
      setPreviewVersion(0);
      setPreviewReady(false);
      loadScope(activeJobId);
      loadStoryboard(activeJobId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update target length");
    } finally {
      setRegenerating(false);
    }
  };

  const hasAssignedClip = Boolean(
    storyboard?.slots.some((slot) => slot.assigned_clip_id),
  );

  const requestTargetChange = (targetDurationS: number, useFullTrack: boolean) => {
    if (
      targetDurationS === form.targetDurationS &&
      useFullTrack === form.useFullTrack
    ) {
      return;
    }
    if (!hasAssignedClip) {
      if (activeJobId) {
        void handleTargetChange(targetDurationS, useFullTrack);
      } else {
        patchForm({ targetDurationS, useFullTrack });
      }
      return;
    }
    setRegeneratePrompt({ targetDurationS, useFullTrack });
  };

  const confirmRegenerate = () => {
    if (!regeneratePrompt) return;
    const pending = regeneratePrompt;
    setRegeneratePrompt(null);
    void handleTargetChange(pending.targetDurationS, pending.useFullTrack);
  };

  const dismissTargetSuggestion = () => {
    if (!targetSuggestionPrompt || !activeJobId) return;
    const { requested, suggested } = targetSuggestionPrompt;
    setDismissedTargetSuggestions((prev) => {
      const next = new Set(prev);
      next.add(`${activeJobId}:${requested}:${suggested}`);
      return next;
    });
    setTargetSuggestionPrompt(null);
  };

  const confirmTargetSuggestion = () => {
    if (!targetSuggestionPrompt || !activeJobId) return;
    const { requested, suggested } = targetSuggestionPrompt;
    setDismissedTargetSuggestions((prev) => {
      const next = new Set(prev);
      next.add(`${activeJobId}:${requested}:${suggested}`);
      return next;
    });
    setTargetSuggestionPrompt(null);
    void handleTargetChange(suggested, false);
  };

  const handleSelectBlock = async (block: MusicBlock) => {
    if (!activeJobId) return;
    setSelectedBlockId(block.id);
    setMusicStartS(block.start_s);
    setMusicEndS(block.end_s);
    try {
      await updateMusicSelection(activeJobId, { selected_block_id: block.id });
      loadScope(activeJobId);
      loadStoryboard(activeJobId);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not select block");
    }
  };

  const handleAssignClip = async (
    slotId: string,
    file: File,
    cropStartS: number,
    cropEndS: number,
    transform?: { rotation_deg?: number; spatial_crop?: { x: number; y: number; w: number; h: number } | null },
  ) => {
    if (!activeJobId) return;
    setStoryboardSaving(true);
    try {
      const payload = await assignSlotClip(
        activeJobId,
        slotId,
        file,
        cropStartS,
        cropEndS,
        transform,
      );
      setStoryboard(payload);
      setPreviewReady(payload.preview_ready);
      setPreviewVersion((v) => v + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign clip");
    } finally {
      setStoryboardSaving(false);
    }
  };

  const handleUpdateSlotCrop = async (
    slotId: string,
    cropStartS: number,
    cropEndS: number,
  ) => {
    if (!activeJobId) return;
    setStoryboardSaving(true);
    try {
      const payload = await updateSlotCrop(activeJobId, slotId, cropStartS, cropEndS);
      setStoryboard(payload);
      setPreviewReady(payload.preview_ready);
      setPreviewVersion((v) => v + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update crop");
    } finally {
      setStoryboardSaving(false);
    }
  };

  const handleUpdateSlotTransform = async (
    slotId: string,
    payload: {
      rotation_deg?: number;
      fit_mode?: "contain" | "cover";
      spatial_crop?: { x: number; y: number; w: number; h: number } | null;
    },
  ) => {
    if (!activeJobId) return;
    setStoryboardSaving(true);
    try {
      const updated = await updateSlotTransform(activeJobId, slotId, payload);
      setStoryboard(updated);
      setPreviewReady(updated.preview_ready);
      setPreviewVersion((v) => v + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update clip transform");
    } finally {
      setStoryboardSaving(false);
    }
  };

  const handleClearClip = async (slotId: string) => {
    if (!activeJobId) return;
    setStoryboardSaving(true);
    try {
      const payload = await clearSlotClip(activeJobId, slotId);
      setStoryboard(payload);
      setPreviewReady(payload.preview_ready);
      setPreviewVersion((v) => v + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not clear clip");
    } finally {
      setStoryboardSaving(false);
    }
  };

  const handlePatchStoryboard = async (payload: Parameters<typeof patchStoryboard>[1]) => {
    if (!activeJobId) return;
    setStoryboardSaving(true);
    try {
      const updated = await patchStoryboard(activeJobId, payload);
      setStoryboard(updated);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update storyboard");
    } finally {
      setStoryboardSaving(false);
    }
  };

  const compositeUrl =
    activeJobId && previewReady
      ? (() => {
          const base = compositePreviewUrl(activeJobId, previewVersion > 0);
          return `${base}${base.includes("?") ? "&" : "?"}v=${previewVersion}`;
        })()
      : null;

  useEffect(() => {
    setBlockPlayheadS(0);
    setCompositePreviewPlaying(false);
  }, [activeJobId, storyboard?.music_start_s, storyboard?.total_duration_s, compositeUrl]);

  return (
    <div className="min-h-screen">
      <header className="border-b border-monitor-border bg-monitor-surface/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-4 px-5 py-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-scope-trace">
              Audio-first storyboard
            </p>
            <h1 className="text-lg font-semibold tracking-tight">Control Room</h1>
          </div>
          <div className="flex items-center gap-3 font-mono text-xs">
            <span
              className={
                apiOnline
                  ? "text-scope-trace"
                  : apiOnline === false
                    ? "text-hook-gold"
                    : "text-monitor-muted"
              }
            >
              {apiOnline === null
                ? "CHECKING API…"
                : apiOnline
                  ? "API ONLINE"
                  : "API OFFLINE"}
            </span>
            <span className="text-monitor-muted">|</span>
            <span
              className={
                ffmpegOk
                  ? "text-scope-trace"
                  : ffmpegOk === false
                    ? "text-hook-gold"
                    : "text-monitor-muted"
              }
            >
              {ffmpegOk === null ? "CHECKING FFMPEG…" : ffmpegOk ? "FFMPEG OK" : "FFMPEG OFFLINE"}
            </span>
          </div>
        </div>
      </header>

      <div className="border-b border-monitor-border bg-monitor-surface/60 backdrop-blur">
        <div className="mx-auto max-w-[1400px] px-5 py-3">
          <StageTelemetry
            stages={stages}
            events={events}
            status={jobStatus}
            hasOutput={hasOutput}
          />
        </div>
      </div>

      <main className="mx-auto grid max-w-[1400px] gap-5 px-5 py-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start">
        <section className="space-y-5">
          <JobForm
            form={form}
            onAudioSelected={handleAudioSelected}
            onTargetDurationChange={(targetDurationS) =>
              requestTargetChange(targetDurationS, false)
            }
            audioName={audioName}
            analyzing={analyzing}
            disabled={apiOnline === false || ffmpegOk === false}
            disabledReason={renderBlockedReason}
            audioScope={
              waveform && activeJobId ? (
                <AudioScopePanel
                  embedded
                  jobId={activeJobId}
                  waveform={waveform}
                  targetDurationS={form.targetDurationS}
                  useFullTrack={form.useFullTrack}
                  selectedBlockId={selectedBlockId}
                  onTargetChange={requestTargetChange}
                  onSelectBlock={handleSelectBlock}
                />
              ) : null
            }
          />

          {storyboard && activeJobId && (
            <>
              <StoryboardPanel
                jobId={activeJobId}
                storyboard={storyboard}
                waveform={waveform}
                selectedSlotId={selectedSlotId}
                onSelectSlot={setSelectedSlotId}
                onAssignClip={handleAssignClip}
                onUpdateSlotCrop={handleUpdateSlotCrop}
                onUpdateSlotTransform={handleUpdateSlotTransform}
                onClearClip={handleClearClip}
                onPatchStoryboard={handlePatchStoryboard}
                saving={storyboardSaving}
                blockPlayheadS={blockPlayheadS}
                onBlockPlayheadChange={setBlockPlayheadS}
                compositePreviewActive={previewReady && compositeUrl != null}
                compositePreviewPlaying={compositePreviewPlaying}
                onToggleCompositePreview={toggleCompositePreview}
                onSeekCompositePreview={seekCompositeFromBlock}
                onPlayCompositePreview={playCompositePreview}
              />
              <HookOverlayPanel form={form} onPatch={patchForm} />
            </>
          )}

          {apiOnline === false && (
            <div
              role="alert"
              className="rounded-md border border-hook-gold/40 bg-hook-gold/10 px-4 py-3 text-sm text-hook-gold"
            >
              Control Room API is not reachable. Run{" "}
              <code className="font-mono text-xs">python -m viral_editor serve</code> and refresh.
              <button type="button" className="btn-ghost ml-3 mt-2 inline-flex text-xs" onClick={loadHealth}>
                Retry
              </button>
            </div>
          )}

          {error && (
            <div
              role="alert"
              className="rounded-md border border-hook-gold/40 bg-hook-gold/10 px-4 py-3 text-sm text-hook-gold"
            >
              {error}
            </div>
          )}

          <OutputPanel
            jobId={activeJobId}
            status={jobStatus}
            hasOutput={hasOutput}
            artifacts={jobArtifacts}
            scopeReady={waveform !== null}
          />
        </section>

        <aside className="sticky top-6 flex max-h-[calc(100vh-1.5rem)] flex-col gap-5 self-start overflow-y-auto">
          <div className="panel flex flex-col items-center px-6 py-8">
            <p className="mb-4 self-start font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
              Composed preview
            </p>
            <PhonePreview
              hookText={form.hookText}
              emphasisWords={form.emphasisWords}
              fillColor={form.fillColor}
              emphasisColor={form.emphasisColor}
              fontFamily={form.fontFamily}
              safePaddingPct={form.safePaddingPct}
              videoPreviewUrl={compositeUrl}
              compositeMode={previewReady}
              storyboard={storyboard}
              onBlockPlayheadChange={setBlockPlayheadS}
              onPreviewPlayingChange={setCompositePreviewPlaying}
              registerPreviewToggle={registerPreviewToggle}
              registerPreviewSeek={registerPreviewSeek}
              registerPreviewPlay={registerPreviewPlay}
            />
            {musicStartS != null && musicEndS != null && (
              <dl className="mt-6 grid w-full grid-cols-2 gap-3 font-mono text-xs">
                <div className="rounded border border-monitor-border bg-monitor-bg px-3 py-2">
                  <dt className="text-monitor-muted">MUSIC WINDOW</dt>
                  <dd className="text-scope-trace">
                    {(musicEndS - musicStartS).toFixed(1)}s
                  </dd>
                </div>
                <div className="rounded border border-monitor-border bg-monitor-bg px-3 py-2">
                  <dt className="text-monitor-muted">STATUS</dt>
                  <dd>{jobStatus ?? "idle"}</dd>
                </div>
              </dl>
            )}
            {previewReady && activeJobId && (
              <button
                type="button"
                className="btn-ghost mt-4 text-xs"
                onClick={() => setPreviewVersion((v) => v + 1)}
              >
                Refresh preview
              </button>
            )}
          </div>
        </aside>
      </main>

      <ConfirmDialog
        open={targetSuggestionPrompt !== null}
        title="No loop at this length"
        message={
          targetSuggestionPrompt
            ? `We couldn't find a phrase-aligned ${targetSuggestionPrompt.requested}s loop in this track. Switch to ${targetSuggestionPrompt.suggested}s for the closest matching short?`
            : ""
        }
        confirmLabel={`Switch to ${targetSuggestionPrompt?.suggested ?? ""}s`}
        cancelLabel={`Keep ${targetSuggestionPrompt?.requested ?? ""}s`}
        onConfirm={confirmTargetSuggestion}
        onCancel={dismissTargetSuggestion}
      />

      <ConfirmDialog
        open={regeneratePrompt !== null}
        title="Regenerate short?"
        message={
          regeneratePrompt
            ? regeneratePrompt.useFullTrack
              ? "Switch to the full track? Music blocks and the storyboard will rebuild — your clip crops may no longer fit."
              : `Change target length to ${regeneratePrompt.targetDurationS}s? Music blocks and the storyboard will rebuild — your clip crops may no longer fit.`
            : ""
        }
        confirmLabel={regenerating ? "Regenerating…" : "Regenerate"}
        cancelLabel="Keep current"
        confirmDisabled={regenerating}
        onConfirm={confirmRegenerate}
        onCancel={() => setRegeneratePrompt(null)}
      />
    </div>
  );
}
