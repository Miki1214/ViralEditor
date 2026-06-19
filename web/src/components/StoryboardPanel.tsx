import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { SlotRole, SlotTransition, StoryboardPayload, StorySlot } from "../types";
import { ClipCropTimeline } from "./ClipCropTimeline";

interface StoryboardPanelProps {
  jobId: string;
  storyboard: StoryboardPayload;
  selectedSlotId: string | null;
  onSelectSlot: (slotId: string) => void;
  onAssignClip: (
    slotId: string,
    file: File,
    cropStartS: number,
    cropEndS: number,
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
}

function isVideoFile(file: File): boolean {
  if (file.type.startsWith("video/")) return true;
  return /\.(mp4|mov|webm|mkv|avi|m4v)$/i.test(file.name);
}

function roleClass(role: SlotRole): string {
  if (role === "hook") return "border-hook-gold bg-hook-gold/10";
  if (role === "punch") return "border-bass-blue bg-bass-blue/10";
  return "border-scope-trace/40 bg-scope-trace/5";
}

export function StoryboardPanel({
  jobId: _jobId,
  storyboard,
  selectedSlotId,
  onSelectSlot,
  onAssignClip,
  onClearClip,
  onPatchStoryboard,
  saving = false,
}: StoryboardPanelProps) {
  const ordered = [...storyboard.slots].sort((a, b) => a.order - b.order);
  const active =
    ordered.find((slot) => slot.id === selectedSlotId) ?? ordered[0] ?? null;

  const [localFile, setLocalFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [durationS, setDurationS] = useState<number | null>(null);
  const [cropStartS, setCropStartS] = useState(0);
  const [cropEndS, setCropEndS] = useState(0);
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!active) return;
    onSelectSlot(active.id);
  }, [active?.id, onSelectSlot]);

  useEffect(() => {
    if (active?.assigned_clip_id && active.clip_source_url) {
      setPreviewUrl(active.clip_source_url);
      setLocalFile(null);
      setDurationS(
        active.crop_end_s != null && active.crop_start_s != null
          ? Math.max(active.crop_end_s, active.target_duration_s * 2)
          : active.target_duration_s * 3,
      );
      setCropStartS(active.crop_start_s ?? 0);
      setCropEndS(active.crop_end_s ?? active.target_duration_s);
      return;
    }
    if (!localFile) {
      setPreviewUrl(null);
      setDurationS(null);
      return;
    }
    const url = URL.createObjectURL(localFile);
    setPreviewUrl(url);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.src = url;
    const apply = () => {
      const duration = Number.isFinite(video.duration) ? video.duration : null;
      setDurationS(duration);
      if (duration != null && active) {
        const span = Math.min(duration, active.target_duration_s);
        setCropStartS(0);
        setCropEndS(span);
      }
    };
    video.addEventListener("loadedmetadata", apply);
    video.addEventListener("error", apply);
    return () => {
      video.removeEventListener("loadedmetadata", apply);
      video.removeEventListener("error", apply);
      URL.revokeObjectURL(url);
    };
  }, [active, localFile]);

  const pickFile = useCallback(
    (files: FileList | File[] | null) => {
      if (!files?.length || !active) return;
      const file = Array.from(files).find(isVideoFile);
      if (!file) return;
      setLocalFile(file);
    },
    [active],
  );

  const commitClip = async () => {
    if (!active || !localFile || durationS == null) return;
    await onAssignClip(active.id, localFile, cropStartS, cropEndS);
    setLocalFile(null);
  };

  const toggleTransition = async (slot: StorySlot) => {
    const next: SlotTransition = slot.transition_in === "xfade" ? "cut" : "xfade";
    await onPatchStoryboard({
      slots: [{ id: slot.id, order: slot.order, transition_in: next }],
    });
  };

  return (
    <div className="panel space-y-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Storyboard
          </h2>
          <p className="mt-1 text-xs text-monitor-muted">
            Drop a clip into each slot — durations follow the music block.
          </p>
        </div>
        <dl className="font-mono text-xs">
          <dt className="text-monitor-muted">TIMELINE</dt>
          <dd className="text-scope-trace">{storyboard.total_duration_s.toFixed(1)}s</dd>
        </dl>
      </div>

      <div className="relative flex gap-2 overflow-x-auto pb-2">
        {ordered.map((slot, index) => {
          const selected = slot.id === active?.id;
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
                className={`min-w-[120px] rounded border p-3 text-left transition ${roleClass(slot.role)} ${
                  selected ? "ring-1 ring-scope-trace" : ""
                } ${!slot.assigned_clip_id ? "opacity-80" : ""}`}
              >
                <p className="font-mono text-[10px] uppercase text-monitor-muted">{slot.label}</p>
                <p className="mt-1 font-mono text-[11px] text-monitor-text">
                  {slot.target_duration_s.toFixed(1)}s
                </p>
                <p className="mt-1 truncate font-mono text-[10px] text-scope-trace">
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
          <div className="flex items-center justify-between gap-2">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-scope-trace">
              {active.label} · {active.target_duration_s.toFixed(1)}s target
            </p>
            {active.assigned_clip_id && (
              <button
                type="button"
                className="btn-ghost text-[10px]"
                disabled={saving}
                onClick={() => void onClearClip(active.id)}
              >
                Clear clip
              </button>
            )}
          </div>

          {!active.assigned_clip_id && (
            <label
              htmlFor={inputId}
              className="flex min-h-[72px] cursor-pointer flex-col items-center justify-center rounded border border-dashed border-monitor-border px-4 py-4 text-center hover:border-scope-dim"
            >
              <input
                ref={inputRef}
                id={inputId}
                type="file"
                accept="video/*,.mp4,.mov,.webm,.mkv"
                className="sr-only"
                onChange={(e) => {
                  pickFile(e.target.files);
                  e.target.value = "";
                }}
              />
              <span className="text-xs text-monitor-muted">
                Drop video for this slot or click to browse
              </span>
            </label>
          )}

          {previewUrl && durationS != null && durationS > 0 && (
            <>
              <ClipCropTimeline
                videoUrl={previewUrl}
                durationS={durationS}
                cropStartS={cropStartS}
                cropEndS={cropEndS}
                onCropChange={(startS, endS) => {
                  setCropStartS(startS);
                  setCropEndS(endS);
                }}
              />
              <p className="font-mono text-[10px] text-monitor-muted">
                Selected {(cropEndS - cropStartS).toFixed(2)}s → fits{" "}
                {active.target_duration_s.toFixed(1)}s slot
                {active.role === "punch" ? " (slow-mo punch)" : ""}
              </p>
              {localFile && (
                <button
                  type="button"
                  className="btn-primary text-xs"
                  disabled={saving}
                  onClick={() => void commitClip()}
                >
                  Assign to slot
                </button>
              )}
              {active.assigned_clip_id && localFile == null && (
                <button
                  type="button"
                  className="btn-primary text-xs"
                  disabled={saving}
                  onClick={() => inputRef.current?.click()}
                >
                  Replace clip
                </button>
              )}
            </>
          )}
        </div>
      )}

      {saving && (
        <p className="font-mono text-[11px] text-monitor-muted">Syncing storyboard…</p>
      )}
    </div>
  );
}
