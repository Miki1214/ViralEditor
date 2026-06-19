import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { SlotFitMode, SlotTransition, SpatialCrop, StoryboardPayload, StorySlot, WaveformPayload } from "../types";
import { slotColorForIndex } from "../utils/slotColors";
import { ClipCropTimeline } from "./ClipCropTimeline";
import { SpatialCropModal } from "./SpatialCropModal";
import { StoryboardBlockPlayer } from "./StoryboardBlockPlayer";
import { StoryboardScopeCanvas } from "./StoryboardScopeCanvas";

interface StoryboardPanelProps {
  jobId: string;
  storyboard: StoryboardPayload;
  waveform: WaveformPayload | null;
  selectedSlotId: string | null;
  onSelectSlot: (slotId: string) => void;
  onAssignClip: (
    slotId: string,
    file: File,
    cropStartS: number,
    cropEndS: number,
    transform?: { rotation_deg?: number; spatial_crop?: SpatialCrop | null },
  ) => Promise<void>;
  onUpdateSlotCrop: (
    slotId: string,
    cropStartS: number,
    cropEndS: number,
  ) => Promise<void>;
  onUpdateSlotTransform: (
    slotId: string,
    payload: {
      rotation_deg?: number;
      fit_mode?: SlotFitMode;
      spatial_crop?: SpatialCrop | null;
    },
  ) => Promise<void>;
  onClearClip: (slotId: string) => Promise<void>;
  onPatchStoryboard: (payload: {
    slots?: Array<{
      id: string;
      order: number;
      transition_in?: SlotTransition;
    }>;
    loop_to_hook?: boolean;
  }) => Promise<void>;
  saving?: boolean;
  blockPlayheadS: number;
  onBlockPlayheadChange: (seconds: number) => void;
  compositePreviewActive?: boolean;
  compositePreviewPlaying?: boolean;
  onToggleCompositePreview?: () => void;
  onSeekCompositePreview?: (blockPlayheadS: number) => void;
  onPlayCompositePreview?: () => void;
}

interface SlotTransformDraft {
  rotation_deg: number;
  spatial_crop: SpatialCrop | null;
}

function transformNeedsSync(transform: SlotTransformDraft): boolean {
  return transform.rotation_deg !== 0 || transform.spatial_crop != null;
}

function isVideoFile(file: File): boolean {
  if (file.type.startsWith("video/")) return true;
  return /\.(mp4|mov|webm|mkv|avi|m4v)$/i.test(file.name);
}

function probeVideoDuration(url: string): Promise<number | null> {
  return new Promise((resolve) => {
    const video = document.createElement("video");
    video.preload = "metadata";
    video.src = url;
    const finish = () => {
      resolve(Number.isFinite(video.duration) ? video.duration : null);
    };
    video.addEventListener("loadedmetadata", finish, { once: true });
    video.addEventListener("error", () => resolve(null), { once: true });
  });
}

export function StoryboardPanel({
  jobId,
  storyboard,
  waveform,
  selectedSlotId,
  onSelectSlot,
  onAssignClip,
  onUpdateSlotCrop,
  onUpdateSlotTransform,
  onClearClip,
  onPatchStoryboard,
  saving = false,
  blockPlayheadS,
  onBlockPlayheadChange,
  compositePreviewActive = false,
  compositePreviewPlaying = false,
  onToggleCompositePreview,
  onSeekCompositePreview,
  onPlayCompositePreview,
}: StoryboardPanelProps) {
  const ordered = [...storyboard.slots].sort((a, b) => a.order - b.order);
  const active =
    ordered.find((slot) => slot.id === selectedSlotId) ?? ordered[0] ?? null;

  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [durationS, setDurationS] = useState<number | null>(null);
  const [cropStartS, setCropStartS] = useState(0);
  const [cropEndS, setCropEndS] = useState(0);
  const [draftTransforms, setDraftTransforms] = useState<Record<string, SlotTransformDraft>>({});
  const [spatialCropOpen, setSpatialCropOpen] = useState(false);
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const assignTargetRef = useRef<StorySlot | null>(null);

  useEffect(() => {
    if (!active) return;
    onSelectSlot(active.id);
  }, [active?.id, onSelectSlot]);

  useEffect(() => {
    if (!active?.assigned_clip_id || !active.clip_source_url) {
      setPreviewUrl(null);
      setDurationS(null);
      return;
    }

    let cancelled = false;
    setPreviewUrl(active.clip_source_url);
    setCropStartS(active.crop_start_s ?? 0);
    setCropEndS(active.crop_end_s ?? active.target_duration_s);

    void probeVideoDuration(active.clip_source_url).then((duration) => {
      if (!cancelled && duration != null) {
        setDurationS(duration);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [active]);

  const assignFileToSlot = useCallback(
    async (file: File, slot: StorySlot) => {
      if (saving) return;
      assignTargetRef.current = slot;
      const objectUrl = URL.createObjectURL(file);
      let endS = slot.target_duration_s;
      try {
        const duration = await probeVideoDuration(objectUrl);
        if (duration != null) {
          endS = Math.min(duration, slot.target_duration_s);
        }
      } finally {
        URL.revokeObjectURL(objectUrl);
      }
      const draft = draftTransforms[slot.id];
      const transform =
        draft && transformNeedsSync(draft)
          ? { rotation_deg: draft.rotation_deg, spatial_crop: draft.spatial_crop }
          : undefined;
      await onAssignClip(slot.id, file, 0, endS, transform);
      if (assignTargetRef.current?.id === slot.id) {
        setDraftTransforms((prev) => {
          const next = { ...prev };
          delete next[slot.id];
          return next;
        });
      }
    },
    [draftTransforms, onAssignClip, saving],
  );

  const pickFile = useCallback(
    (files: FileList | File[] | null, slot: StorySlot | null = active) => {
      if (!files?.length || !slot) return;
      const file = Array.from(files).find(isVideoFile);
      if (!file) return;
      void assignFileToSlot(file, slot);
    },
    [active, assignFileToSlot],
  );

  const handleFileInput = useCallback(
    (files: FileList | null) => {
      pickFile(files);
    },
    [pickFile],
  );

  const handleDrop = useCallback(
    (event: React.DragEvent, slot: StorySlot | null = active) => {
      event.preventDefault();
      pickFile(event.dataTransfer.files, slot);
    },
    [active, pickFile],
  );

  const commitCrop = async (startS: number, endS: number) => {
    if (!active?.assigned_clip_id) return;
    const unchanged =
      active.crop_start_s === startS && active.crop_end_s === endS;
    if (unchanged) return;
    await onUpdateSlotCrop(active.id, startS, endS);
  };

  const toggleTransition = async (slot: StorySlot) => {
    const next: SlotTransition = slot.transition_in === "xfade" ? "cut" : "xfade";
    await onPatchStoryboard({
      slots: [{ id: slot.id, order: slot.order, transition_in: next }],
    });
  };

  const activeSlotIndex = active ? ordered.findIndex((slot) => slot.id === active.id) : -1;
  const activeSlotColor = activeSlotIndex >= 0 ? slotColorForIndex(activeSlotIndex) : null;

  const slotTransform = useCallback(
    (slot: StorySlot): SlotTransformDraft => {
      if (slot.assigned_clip_id) {
        return {
          rotation_deg: slot.rotation_deg ?? 0,
          spatial_crop: slot.spatial_crop ?? null,
        };
      }
      return (
        draftTransforms[slot.id] ?? {
          rotation_deg: 0,
          spatial_crop: null,
        }
      );
    },
    [draftTransforms],
  );

  const applySlotTransform = useCallback(
    (
      slot: StorySlot,
      update: {
        rotation_deg?: number;
        spatial_crop?: SpatialCrop | null;
      },
    ) => {
      const current = slotTransform(slot);
      const next: SlotTransformDraft = {
        rotation_deg: update.rotation_deg ?? current.rotation_deg,
        spatial_crop: update.spatial_crop !== undefined ? update.spatial_crop : current.spatial_crop,
      };
      if (slot.assigned_clip_id) {
        void onUpdateSlotTransform(slot.id, update);
        return;
      }
      setDraftTransforms((prev) => ({ ...prev, [slot.id]: next }));
    },
    [onUpdateSlotTransform, slotTransform],
  );

  const clearActiveClip = useCallback(() => {
    if (!active?.assigned_clip_id) return;
    void onClearClip(active.id);
  }, [active, onClearClip]);

  const activeTransform = active ? slotTransform(active) : null;
  const canClearClip = Boolean(active?.assigned_clip_id);

  return (
    <div className="panel space-y-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Storyboard
          </h2>
          <p className="mt-1 text-xs text-monitor-muted">
            Drop a clip into each slot — it uploads and assigns automatically.
          </p>
        </div>
        <dl className="font-mono text-xs">
          <dt className="text-monitor-muted">TIMELINE</dt>
          <dd className="text-scope-trace">{storyboard.total_duration_s.toFixed(1)}s</dd>
        </dl>
      </div>

      {waveform && (
        <div className="space-y-2">
          <StoryboardScopeCanvas
            waveform={waveform}
            storyboard={storyboard}
            selectedSlotId={selectedSlotId}
            playheadS={blockPlayheadS}
            onSelectSlot={onSelectSlot}
          />
          <StoryboardBlockPlayer
            jobId={jobId}
            storyboard={storyboard}
            selectedSlotId={selectedSlotId}
            playheadS={blockPlayheadS}
            onPlayheadChange={onBlockPlayheadChange}
            onSelectSlot={onSelectSlot}
            compositePreviewActive={compositePreviewActive}
            compositePreviewPlaying={compositePreviewPlaying}
            onToggleCompositePreview={onToggleCompositePreview}
            onSeekCompositePreview={onSeekCompositePreview}
            onPlayCompositePreview={onPlayCompositePreview}
          />
        </div>
      )}

      <div className="relative flex gap-2 overflow-x-auto pb-2">
        {ordered.map((slot, index) => {
          const selected = slot.id === active?.id;
          const color = slotColorForIndex(index);
          return (
            <div key={slot.id} className="flex shrink-0 items-center gap-1">
              {index > 0 && (
                <button
                  type="button"
                  className="font-mono text-[9px] uppercase text-monitor-muted hover:text-scope-trace"
                  title={`Transition: ${slot.transition_in}`}
                  onClick={() => void toggleTransition(slot)}
                  disabled={saving}
                >
                  {slot.transition_in === "xfade" ? "◆" : "|"}
                </button>
              )}
              <button
                type="button"
                onClick={() => onSelectSlot(slot.id)}
                className={`min-w-[120px] rounded border p-3 text-left transition ${
                  !slot.assigned_clip_id ? "opacity-80" : ""
                }`}
                style={{
                  borderColor: selected ? color.stroke : color.border,
                  backgroundColor: selected ? color.fillActive : color.bg,
                  boxShadow: selected ? `0 0 0 1px ${color.stroke}` : undefined,
                }}
              >
                <p className="flex items-center gap-1.5 font-mono text-[10px] uppercase text-monitor-muted">
                  <span
                    className="inline-block h-2 w-2 shrink-0 rounded-full"
                    style={{ backgroundColor: color.stroke }}
                    aria-hidden
                  />
                  {slot.label}
                </p>
                <p className="mt-1 font-mono text-[11px] text-monitor-text">
                  {slot.target_duration_s.toFixed(1)}s
                </p>
                <p
                  className="mt-1 truncate font-mono text-[10px]"
                  style={{ color: color.stroke }}
                >
                  {slot.clip_filename ?? (slot.assigned_clip_id ? "assigned" : "empty")}
                </p>
              </button>
            </div>
          );
        })}
        {storyboard.loop_to_hook && ordered.length > 0 && (
          <div className="flex shrink-0 items-center pl-2 font-mono text-[10px] text-hook-gold">
            ↩ loop to hook
          </div>
        )}
      </div>

      {active && (
        <div className="rounded border border-monitor-border bg-monitor-bg/40 p-4 space-y-3">
          <input
            ref={inputRef}
            id={inputId}
            type="file"
            accept="video/*,.mp4,.mov,.webm,.mkv"
            className="sr-only"
            disabled={saving}
            onChange={(e) => {
              handleFileInput(e.target.files);
              e.target.value = "";
            }}
          />
          <div className="flex items-center justify-between gap-2">
            <p
              className="font-mono text-[10px] uppercase tracking-[0.18em]"
              style={{ color: activeSlotColor?.stroke ?? undefined }}
            >
              {active.label} · {active.target_duration_s.toFixed(1)}s target
            </p>
            {activeTransform && (
              <div className="flex shrink-0 items-center gap-1.5">
                <button
                  type="button"
                  className="btn-ghost px-2 py-1 font-mono text-[10px]"
                  disabled={saving}
                  title="Rotate clip 90° clockwise"
                  onClick={() =>
                    applySlotTransform(active, {
                      rotation_deg: (activeTransform.rotation_deg + 90) % 360,
                    })
                  }
                >
                  ↻ 90°
                </button>
                <button
                  type="button"
                  className={`btn-ghost px-2 py-1 font-mono text-[10px] ${
                    activeTransform.spatial_crop ? "text-scope-trace" : ""
                  }`}
                  disabled={saving || !previewUrl}
                  title="Open frame crop editor (9:16)"
                  onClick={() => setSpatialCropOpen(true)}
                >
                  Frame crop
                </button>
                {canClearClip && (
                  <button
                    type="button"
                    className="btn-ghost text-[10px]"
                    disabled={saving}
                    onClick={clearActiveClip}
                  >
                    Clear clip
                  </button>
                )}
              </div>
            )}
          </div>

          {!active.assigned_clip_id && (
            <label
              htmlFor={inputId}
              className="flex min-h-[72px] cursor-pointer flex-col items-center justify-center rounded border border-dashed border-monitor-border px-4 py-4 text-center hover:border-scope-dim"
              onDrop={(event) => handleDrop(event)}
              onDragOver={(event) => event.preventDefault()}
            >
              <span className="text-xs text-monitor-muted">
                {saving ? "Uploading clip…" : "Drop video for this slot or click to browse"}
              </span>
            </label>
          )}

          {previewUrl && durationS != null && durationS > 0 && (
            <div
              onDrop={(event) => handleDrop(event)}
              onDragOver={(event) => event.preventDefault()}
            >
              <ClipCropTimeline
                durationS={durationS}
                cropStartS={cropStartS}
                cropEndS={cropEndS}
                targetDurationS={active.target_duration_s}
                slotRole={active.role}
                onCropChange={(startS, endS) => {
                  setCropStartS(startS);
                  setCropEndS(endS);
                }}
                onCropCommit={(startS, endS) => {
                  void commitCrop(startS, endS);
                }}
              />
            </div>
          )}
        </div>
      )}

      {active && previewUrl && (
        <SpatialCropModal
          open={spatialCropOpen}
          videoUrl={previewUrl}
          rotationDeg={activeTransform?.rotation_deg ?? 0}
          initialCrop={activeTransform?.spatial_crop ?? null}
          onClose={() => setSpatialCropOpen(false)}
          onApply={(crop) => {
            applySlotTransform(active, { spatial_crop: crop });
            setSpatialCropOpen(false);
          }}
        />
      )}

      {saving && (
        <p className="font-mono text-[11px] text-monitor-muted">Syncing storyboard…</p>
      )}
    </div>
  );
}
