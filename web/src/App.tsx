import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { JobSummary, MusicBlock, PipelineEvent, StageInfo, StoryboardPayload, WaveformPayload } from "./types";
import {
  assignSlotClip,
  clearSlotClip,
  compositePreviewUrl,
  createDraftJob,
  fetchCompositePreview,
  fetchHealth,
  fetchJobs,
  fetchStages,
  fetchStoryboard,
  fetchWaveform,
  patchEffects,
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
import { DebugConsolePanel } from "./components/DebugConsolePanel";
import { PhonePreview, type PreviewTransportRestore } from "./components/PhonePreview";
import {
  installDebugConsoleCapture,
  isDebugMode,
  pushDebugLog,
} from "./utils/debugLog";
import { emitPlayheadUi } from "./utils/playheadBus";
import type {
  BlockPlayheadChangeHandler,
  StoryboardLoopMode,
} from "./components/StoryboardBlockPlayer";
import { StageTelemetry } from "./components/StageTelemetry";
import { StoryboardPanel } from "./components/StoryboardPanel";

const initialForm: FormState = {
  projectName: "",
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
  const [jobs, setJobs] = useState<JobSummary[]>([]);
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
  const [validatedPreviewUrl, setValidatedPreviewUrl] = useState<string | null>(null);
  const [previewLoadError, setPreviewLoadError] = useState<string | null>(null);
  const debugMode = isDebugMode();
  const [restoreMenuOpen, setRestoreMenuOpen] = useState(false);
  const [restoreLoading, setRestoreLoading] = useState(false);
  const restoreMenuRef = useRef<HTMLDivElement | null>(null);
  const [blockPlayheadS, setBlockPlayheadS] = useState(0);
  const blockPlayheadRef = useRef(0);
  const [compositePreviewPlaying, setCompositePreviewPlaying] = useState(false);
  const [previewLoopMode, setPreviewLoopMode] = useState<StoryboardLoopMode>("block");
  const blockSeekRef = useRef<((timeS: number) => void) | null>(null);
  const blockPauseRef = useRef<(() => void) | null>(null);
  const blockPlaySlotRef = useRef<((slotId: string) => void) | null>(null);
  const blockSetLoopModeRef = useRef<((mode: StoryboardLoopMode) => void) | null>(null);
  const registerBlockSeek = useCallback((handler: ((timeS: number) => void) | null) => {
    blockSeekRef.current = handler;
  }, []);
  const registerBlockPause = useCallback((handler: (() => void) | null) => {
    blockPauseRef.current = handler;
  }, []);
  const registerBlockPlaySlot = useCallback((handler: ((slotId: string) => void) | null) => {
    blockPlaySlotRef.current = handler;
  }, []);
  const seekBlockPlayhead = useCallback((timeS: number) => {
    blockSeekRef.current?.(timeS);
  }, []);
  const pauseBlockPlayback = useCallback(() => {
    blockPauseRef.current?.();
  }, []);
  const playBlockSlot = useCallback((slotId: string) => {
    blockPlaySlotRef.current?.(slotId);
  }, []);
  const registerBlockSetLoopMode = useCallback((handler: ((mode: StoryboardLoopMode) => void) | null) => {
    blockSetLoopModeRef.current = handler;
  }, []);
  const togglePreviewRef = useRef<(() => void) | null>(null);
  const seekPreviewRef = useRef<((videoTimeS: number) => void) | null>(null);
  const playPreviewRef = useRef<(() => void) | null>(null);
  const previewRestoreRef = useRef<PreviewTransportRestore | null>(null);
  const activeJobIdRef = useRef<string | null>(null);
  const eventsUnsubRef = useRef<(() => void) | null>(null);

  activeJobIdRef.current = activeJobId;
  blockPlayheadRef.current = blockPlayheadS;

  const handleBlockPlayheadChange = useCallback<BlockPlayheadChangeHandler>(
    (timeS, options) => {
      blockPlayheadRef.current = timeS;
      emitPlayheadUi(timeS);
      if (options?.commit !== false) {
        setBlockPlayheadS(timeS);
      }
    },
    [],
  );

  const capturePreviewTransport = useCallback(
    (overrides: Partial<PreviewTransportRestore> = {}) => {
      previewRestoreRef.current = {
        playheadS: blockPlayheadRef.current,
        playing: compositePreviewPlaying,
        loopMode: previewLoopMode,
        selectedSlotId,
        ...overrides,
      };
    },
    [compositePreviewPlaying, previewLoopMode, selectedSlotId],
  );

  const refreshPreview = useCallback(
    (overrides: Partial<PreviewTransportRestore> = {}) => {
      capturePreviewTransport(overrides);
      setPreviewVersion((v) => v + 1);
    },
    [capturePreviewTransport],
  );

  const applyPreviewRestore = useCallback((restore: PreviewTransportRestore) => {
    setPreviewLoopMode(restore.loopMode);
    blockSetLoopModeRef.current?.(restore.loopMode);
    if (restore.selectedSlotId) {
      setSelectedSlotId(restore.selectedSlotId);
    }
    blockSeekRef.current?.(restore.playheadS);
  }, []);

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

  const refreshJobsList = useCallback(async () => {
    try {
      const list = await fetchJobs();
      setJobs(list);
      return list;
    } catch {
      return [];
    }
  }, []);

  const restoreJob = useCallback(
    async (job: JobSummary) => {
      eventsUnsubRef.current?.();
      eventsUnsubRef.current = null;
      previewRestoreRef.current = null;
      setError(null);
      setAnalyzing(false);
      setRestoreLoading(true);
      setRestoreMenuOpen(false);
      setEvents([]);
      setSelectedSlotId(null);
      setActiveJobId(job.id);
      setJobStatus(job.status);
      setJobArtifacts(job.artifacts);
      setHasOutput(job.has_output);
      patchForm({ projectName: job.project_name });
      setPreviewLoopMode("block");
      blockSetLoopModeRef.current?.("block");
      setPreviewVersion(0);
      setPreviewReady(false);
      setCompositePreviewPlaying(false);
      blockPauseRef.current?.();
      setBlockPlayheadS(0);
      blockPlayheadRef.current = 0;
      emitPlayheadUi(0);
      blockSeekRef.current?.(0);
      try {
        await Promise.all([loadScope(job.id), loadStoryboard(job.id)]);
      } finally {
        setRestoreLoading(false);
      }
    },
    [],
  );

  const jobDisplayTitle = useCallback((job: JobSummary) => {
    const projectName = job.project_name.trim();
    if (projectName) {
      return projectName;
    }
    const hook = job.hook_text.trim();
    if (hook && hook !== initialForm.hookText) {
      return hook;
    }
    const shortId = job.id.slice(0, 8);
    if (job.output_duration_s != null) {
      return `Project ${shortId} · ${job.output_duration_s.toFixed(1)}s cut`;
    }
    return `Project ${shortId}`;
  }, []);

  const formatJobCreatedAt = useCallback((timestampS: number) => {
    return new Date(timestampS * 1000).toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }, []);

  const jobsForRestore = useMemo(() => jobs, [jobs]);

  useEffect(() => {
    loadHealth();
    fetchStages().then(setStages).catch(() => undefined);
    void refreshJobsList();
  }, [refreshJobsList]);

  useEffect(() => {
    if (!restoreMenuOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (!(target instanceof Node)) return;
      if (restoreMenuRef.current?.contains(target)) return;
      setRestoreMenuOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setRestoreMenuOpen(false);
      }
    };
    window.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [restoreMenuOpen]);

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
    return fetchWaveform(jobId)
      .then((payload) => {
        if (activeJobIdRef.current !== jobId) return;
        setWaveform(payload);
        setSelectedBlockId(payload.selected_block_id);
        const selected = payload.blocks.find((block) => block.id === payload.selected_block_id);
        if (selected) {
          setMusicStartS(selected.start_s);
          setMusicEndS(selected.end_s);
        }
      })
      .catch(() => {
        return new Promise<void>((resolve, reject) => {
          window.setTimeout(() => {
            fetchWaveform(jobId)
            .then((payload) => {
              if (activeJobIdRef.current !== jobId) return;
              setWaveform(payload);
              setSelectedBlockId(payload.selected_block_id);
              resolve();
            })
            .catch((err) => {
              if (activeJobIdRef.current !== jobId) return;
              setError(err instanceof Error ? err.message : "Could not load audio scope");
              reject(err);
            });
          }, 500);
        });
      });
  };

  const loadStoryboard = (jobId: string) => {
    return fetchStoryboard(jobId)
      .then((payload) => {
        if (activeJobIdRef.current !== jobId) return;
        setStoryboard(payload);
        setPreviewReady(payload.preview_ready);
        setSelectedSlotId((current) => current ?? payload.slots[0]?.id ?? null);
      })
      .catch(() => {
        if (activeJobIdRef.current !== jobId) return;
        setStoryboard(null);
      });
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
    eventsUnsubRef.current?.();
    eventsUnsubRef.current = null;

    try {
      const { id } = await createDraftJob({
        audio: file,
        projectName: form.projectName,
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

      eventsUnsubRef.current = subscribeJobEvents(
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
          refreshJobsList()
            .then((list) => {
              const job = list.find((j) => j.id === id);
              if (job) {
                setJobStatus(job.status);
                setJobArtifacts(job.artifacts);
                setHasOutput(job.has_output);
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

  const autoTargetSwitchRef = useRef<string | null>(null);
  const handleTargetChangeRef = useRef(handleTargetChange);
  handleTargetChangeRef.current = handleTargetChange;

  useEffect(() => {
    autoTargetSwitchRef.current = null;
  }, [activeJobId]);

  useEffect(() => {
    if (!activeJobId || !waveform || form.useFullTrack || analyzing || regenerating) {
      return;
    }
    if (waveform.target_match_failed !== true) {
      return;
    }
    if (waveform.duration_s <= form.targetDurationS) {
      return;
    }
    const suggested = waveform.suggested_target_duration_s;
    if (suggested == null) {
      return;
    }
    const suggestedRounded = Math.round(suggested);
    if (suggestedRounded === form.targetDurationS) {
      return;
    }

    const switchKey = `${activeJobId}:${form.targetDurationS}->${suggestedRounded}`;
    if (autoTargetSwitchRef.current === switchKey) {
      return;
    }
    autoTargetSwitchRef.current = switchKey;

    void handleTargetChangeRef.current(suggestedRounded, false);
  }, [
    activeJobId,
    analyzing,
    form.targetDurationS,
    form.useFullTrack,
    regenerating,
    waveform,
  ]);

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

  const handleSelectBlock = async (block: MusicBlock) => {
    if (!activeJobId) return;
    setSelectedBlockId(block.id);
    setMusicStartS(block.start_s);
    setMusicEndS(block.end_s);
    setBlockPlayheadS(0);
    blockPlayheadRef.current = 0;
    emitPlayheadUi(0);
    blockSeekRef.current?.(0);
    setCompositePreviewPlaying(false);
    setPreviewReady(false);
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
      const slot = payload.slots.find((item) => item.id === slotId);
      refreshPreview({
        playheadS: slot?.out_start_s ?? blockPlayheadS,
        selectedSlotId: slotId,
      });
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
      refreshPreview();
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
      refreshPreview();
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
      refreshPreview();
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

  const handlePatchEffects = async (
    payload: Parameters<typeof patchEffects>[1],
  ) => {
    if (!activeJobId) return;
    setStoryboardSaving(true);
    try {
      const updated = await patchEffects(activeJobId, payload);
      setStoryboard(updated);
      refreshPreview();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update retention FX");
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
    if (!debugMode) return;
    pushDebugLog("info", "app", "Debug mode enabled");
    return installDebugConsoleCapture();
  }, [debugMode]);

  useEffect(() => {
    if (error && debugMode) {
      pushDebugLog("error", "app", error);
    }
  }, [error, debugMode]);

  useEffect(() => {
    if (!activeJobId || !previewReady || !compositeUrl) {
      setValidatedPreviewUrl(null);
      setPreviewLoadError(null);
      return;
    }

    let cancelled = false;
    let objectUrl: string | null = null;
    const force = previewVersion > 0;

    void (async () => {
      if (debugMode) {
        pushDebugLog("info", "preview", "Fetching composite preview…", compositeUrl);
        const result = await fetchCompositePreview(activeJobId, force);
        if (cancelled) return;
        if (!result.ok) {
          pushDebugLog("error", "preview", `HTTP ${result.status}`, result.detail);
          setPreviewLoadError(result.detail);
          setValidatedPreviewUrl(null);
          return;
        }
        objectUrl = URL.createObjectURL(result.blob);
        pushDebugLog(
          "info",
          "preview",
          `Preview loaded (${Math.round(result.blob.size / 1024)} KB)`,
        );
        setPreviewLoadError(null);
        setValidatedPreviewUrl(objectUrl);
        return;
      }

      setPreviewLoadError(null);
      setValidatedPreviewUrl(compositeUrl);
    })();

    return () => {
      cancelled = true;
      if (objectUrl) {
        URL.revokeObjectURL(objectUrl);
      }
    };
  }, [activeJobId, previewReady, previewVersion, compositeUrl, debugMode]);

  const phonePreviewUrl = debugMode ? validatedPreviewUrl : compositeUrl;

  useEffect(() => {
    setBlockPlayheadS(0);
    blockPlayheadRef.current = 0;
    emitPlayheadUi(0);
    blockSeekRef.current?.(0);
    setCompositePreviewPlaying(false);
  }, [activeJobId, storyboard?.music_start_s, storyboard?.total_duration_s, phonePreviewUrl]);

  return (
    <div className="min-h-screen">
      <header className="relative z-30 border-b border-monitor-border bg-monitor-surface/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] items-center justify-between gap-4 px-5 py-4">
          <div>
            <p className="font-mono text-[10px] uppercase tracking-[0.28em] text-scope-trace">
              Audio-first storyboard
            </p>
            <h1 className="text-lg font-semibold tracking-tight">Control Room</h1>
          </div>
          <div className="flex items-center gap-3">
            <div ref={restoreMenuRef} className="relative">
              <button
                type="button"
                className="btn-ghost px-3 py-1.5 font-mono text-xs"
                onClick={() => setRestoreMenuOpen((open) => !open)}
                disabled={restoreLoading || jobs.length === 0}
              >
                {restoreLoading ? "Restoring…" : "Restore project"}
              </button>
              {restoreMenuOpen && (
                <div className="absolute right-0 top-full z-50 mt-2 w-80 rounded border border-monitor-border bg-monitor-surface p-2 shadow-phone">
                  <div className="mb-2 flex items-center justify-between px-2">
                    <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-monitor-muted">
                      Previous projects
                    </p>
                    <button
                      type="button"
                      className="font-mono text-[10px] text-monitor-muted hover:text-monitor-text"
                      onClick={() => void refreshJobsList()}
                    >
                      Refresh
                    </button>
                  </div>
                  <div className="max-h-72 space-y-1 overflow-y-auto">
                    {jobsForRestore.length === 0 ? (
                      <p className="px-2 py-3 text-xs text-monitor-muted">No saved jobs yet.</p>
                    ) : (
                      jobsForRestore.map((job) => (
                        <button
                          key={job.id}
                          type="button"
                          className={`w-full rounded border px-3 py-2 text-left transition ${
                            job.id === activeJobId
                              ? "border-scope-trace/60 bg-scope-trace/10"
                              : "border-monitor-border bg-monitor-bg/40 hover:border-monitor-text/40"
                          }`}
                          onClick={() => void restoreJob(job)}
                        >
                          <p className="truncate font-mono text-[11px] text-monitor-text">
                            {jobDisplayTitle(job)}
                          </p>
                          <p className="mt-1 font-mono text-[10px] text-monitor-muted">
                            {job.status.toUpperCase()}
                            {job.created_at ? ` · ${formatJobCreatedAt(job.created_at)}` : ""}
                            {job.output_duration_s != null
                              ? ` · ${job.output_duration_s.toFixed(1)}s`
                              : ""}
                            {job.has_output ? " · output ready" : ""}
                          </p>
                          <p className="mt-0.5 truncate font-mono text-[10px] text-monitor-muted/80">
                            {job.hook_text || job.id}
                          </p>
                        </button>
                      ))
                    )}
                  </div>
                </div>
              )}
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
            projectName={form.projectName}
            onProjectNameChange={(projectName) => patchForm({ projectName })}
            onAudioSelected={handleAudioSelected}
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
                  switchingTarget={regenerating}
                />
              ) : analyzing && activeJobId ? (
                <section className="space-y-4 pt-4">
                  <p className="text-xs uppercase tracking-widest text-scope-dim">Audio scope</p>
                  <p className="text-sm text-scope-dim">Analyzing track…</p>
                </section>
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
                onPatchEffects={handlePatchEffects}
                saving={storyboardSaving}
                blockPlayheadS={blockPlayheadS}
                onBlockPlayheadChange={handleBlockPlayheadChange}
                compositePreviewActive={previewReady && phonePreviewUrl != null}
                compositePreviewPlaying={compositePreviewPlaying}
                onToggleCompositePreview={toggleCompositePreview}
                onSeekCompositePreview={seekCompositeFromBlock}
                onPlayCompositePreview={playCompositePreview}
                onLoopModeChange={setPreviewLoopMode}
                onSeekBlockPlayhead={seekBlockPlayhead}
                onPauseBlockPlayback={pauseBlockPlayback}
                onPlayBlockSlot={playBlockSlot}
                registerBlockSeek={registerBlockSeek}
                registerBlockPause={registerBlockPause}
                registerBlockPlaySlot={registerBlockPlaySlot}
                registerBlockSetLoopMode={registerBlockSetLoopMode}
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
              videoPreviewUrl={phonePreviewUrl}
              loadErrorMessage={previewLoadError}
              compositeMode={previewReady}
              storyboard={storyboard}
              loopMode={previewLoopMode}
              selectedSlotId={selectedSlotId}
              onBlockPlayheadChange={handleBlockPlayheadChange}
              onPreviewPlayingChange={setCompositePreviewPlaying}
              previewRestoreRef={previewRestoreRef}
              onApplyPreviewRestore={applyPreviewRestore}
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
                onClick={() => refreshPreview()}
              >
                Refresh preview
              </button>
            )}
            {debugMode && <DebugConsolePanel />}
          </div>
        </aside>
      </main>

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
