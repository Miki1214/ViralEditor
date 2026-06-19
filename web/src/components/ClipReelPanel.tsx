import { useMemo, useState } from "react";
import type { ClipInfo, ClipRole, ClipReelResponse } from "../types";
import { ClipCropTimeline } from "./ClipCropTimeline";

export interface LocalClipDraft {
  id: string;
  file: File;
  order: number;
  included: boolean;
  role: ClipRole;
  cropStartS: number | null;
  cropEndS: number | null;
  durationS: number | null;
  previewUrl: string;
}

interface ClipReelPanelProps {
  mode: "local" | "remote";
  jobId?: string;
  clips: LocalClipDraft[] | ClipInfo[];
  reelDurationS?: number;
  targetBodyDurationS?: number | null;
  selectedClipId?: string | null;
  onSelectClip?: (id: string) => void;
  onReorder?: (clips: LocalClipDraft[] | ClipInfo[]) => void;
  onPatchClip?: (id: string, patch: Partial<ClipInfo>) => void;
  onLocalChange?: (update: import("../hooks/useLocalClipDrafts").LocalClipsUpdater) => void;
  saving?: boolean;
}

function cropDuration(clip: LocalClipDraft | ClipInfo): number {
  const start =
    clip.cropStartS ??
    ("crop_start_s" in clip ? clip.crop_start_s : null) ??
    0;
  const end =
    clip.cropEndS ??
    ("crop_end_s" in clip ? clip.crop_end_s : null) ??
    clip.durationS ??
    ("duration_s" in clip ? clip.duration_s : null) ??
    0;
  return Math.max(0, end - start);
}

export function ClipReelPanel({
  mode,
  jobId,
  clips,
  reelDurationS = 0,
  targetBodyDurationS,
  selectedClipId,
  onSelectClip,
  onReorder,
  onPatchClip,
  onLocalChange,
  saving,
}: ClipReelPanelProps) {
  const ordered = useMemo(
    () => [...clips].sort((a, b) => a.order - b.order),
    [clips],
  );

  const activeId = selectedClipId ?? ordered[0]?.id ?? null;
  const activeClip = ordered.find((clip) => clip.id === activeId) ?? null;

  const includedDuration = useMemo(
    () =>
      ordered
        .filter((clip) => clip.included && clip.role === "clip")
        .reduce((sum, clip) => sum + cropDuration(clip), 0),
    [ordered],
  );

  const moveClip = (id: string, direction: -1 | 1) => {
    const index = ordered.findIndex((clip) => clip.id === id);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= ordered.length) return;
    const next = [...ordered];
    const [item] = next.splice(index, 1);
    next.splice(target, 0, item);
    const reordered = next.map((clip, order) => ({ ...clip, order }));
    if (mode === "local") {
      onLocalChange?.(reordered as LocalClipDraft[]);
    } else {
      onReorder?.(reordered as ClipInfo[]);
    }
  };

  const patch = (id: string, partial: Partial<ClipInfo & LocalClipDraft>) => {
    if (mode === "local") {
      const next = ordered.map((clip) =>
        clip.id === id ? { ...clip, ...partial } : clip,
      );
      onLocalChange?.(next as LocalClipDraft[]);
      return;
    }
    onPatchClip?.(id, partial);
  };

  const [expandedCrop, setExpandedCrop] = useState(true);

  return (
    <div className="panel space-y-4 p-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Clip Reel
          </h2>
          <p className="mt-1 text-xs text-monitor-muted">
            Ordered filmstrip — hook drives teaser + loop fill.
          </p>
        </div>
        <dl className="flex gap-4 font-mono text-xs">
          <div>
            <dt className="text-monitor-muted">REEL</dt>
            <dd className="text-scope-trace">
              {(reelDurationS || includedDuration).toFixed(1)}s
            </dd>
          </div>
          {targetBodyDurationS != null && (
            <div>
              <dt className="text-monitor-muted">TARGET</dt>
              <dd
                className={
                  reelDurationS + 1e-3 < (targetBodyDurationS ?? 0) * (ordered[0] ? 1 : 1)
                    ? "text-hook-gold"
                    : "text-scope-trace"
                }
              >
                {targetBodyDurationS.toFixed(1)}s
              </dd>
            </div>
          )}
        </dl>
      </div>

      <div className="flex gap-2 overflow-x-auto pb-2">
        {ordered.map((clip, index) => {
          const selected = clip.id === activeId;
          const roleClass =
            clip.role === "hook"
              ? "border-hook-gold bg-hook-gold/10"
              : clip.role === "filler"
                ? "border-monitor-border/60 bg-monitor-bg/50 opacity-80"
                : selected
                  ? "border-scope-trace bg-scope-trace/10"
                  : "border-monitor-border bg-monitor-bg";
          return (
            <div
              key={clip.id}
              className={`min-w-[140px] shrink-0 rounded border p-3 transition ${roleClass} ${
                !clip.included ? "opacity-40" : ""
              }`}
            >
              <button
                type="button"
                className="w-full text-left"
                onClick={() => onSelectClip?.(clip.id)}
              >
                <p className="truncate font-mono text-[11px] text-monitor-text">
                  {"file" in clip ? clip.file.name : clip.filename}
                </p>
                <p className="mt-1 font-mono text-[10px] uppercase text-monitor-muted">
                  {clip.role} · {cropDuration(clip).toFixed(1)}s
                </p>
              </button>
              <div className="mt-2 flex flex-wrap gap-1">
                <button
                  type="button"
                  className="rounded border border-monitor-border px-1.5 py-0.5 font-mono text-[10px] text-monitor-muted hover:border-scope-dim"
                  onClick={() => moveClip(clip.id, -1)}
                  disabled={index === 0 || saving}
                  aria-label="Move earlier"
                >
                  ◀
                </button>
                <button
                  type="button"
                  className="rounded border border-monitor-border px-1.5 py-0.5 font-mono text-[10px] text-monitor-muted hover:border-scope-dim"
                  onClick={() => moveClip(clip.id, 1)}
                  disabled={index === ordered.length - 1 || saving}
                  aria-label="Move later"
                >
                  ▶
                </button>
                <select
                  className="field-select !py-0.5 !text-[10px]"
                  value={clip.role}
                  disabled={saving}
                  onChange={(e) =>
                    patch(clip.id, { role: e.target.value as ClipRole })
                  }
                >
                  <option value="clip">Clip</option>
                  <option value="hook">Hook</option>
                  <option value="filler">Filler</option>
                </select>
                <label className="flex items-center gap-1 font-mono text-[10px] text-monitor-muted">
                  <input
                    type="checkbox"
                    checked={clip.included}
                    disabled={saving}
                    onChange={(e) => patch(clip.id, { included: e.target.checked })}
                  />
                  In
                </label>
              </div>
            </div>
          );
        })}
      </div>

      {activeClip && expandedCrop && (
        <div className="rounded border border-monitor-border bg-monitor-bg/40 p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-scope-trace">
              Crop — {"file" in activeClip ? activeClip.file.name : activeClip.filename}
            </p>
            <button
              type="button"
              className="btn-ghost text-[10px]"
              onClick={() => setExpandedCrop(false)}
            >
              Collapse
            </button>
          </div>
          {activeClip.durationS != null && activeClip.durationS > 0 && (
            <ClipCropTimeline
              videoUrl={
                "previewUrl" in activeClip
                  ? activeClip.previewUrl
                  : jobId
                    ? `/api/jobs/${jobId}/clips/${activeClip.id}/source`
                    : ""
              }
              durationS={activeClip.durationS}
              cropStartS={activeClip.cropStartS ?? 0}
              cropEndS={activeClip.cropEndS ?? activeClip.durationS}
              onCropChange={(startS, endS) =>
                patch(activeClip.id, { cropStartS: startS, cropEndS: endS })
              }
            />
          )}
        </div>
      )}

      {activeClip && !expandedCrop && (
        <button
          type="button"
          className="btn-ghost text-xs"
          onClick={() => setExpandedCrop(true)}
        >
          Show crop timeline
        </button>
      )}

      {saving && (
        <p className="font-mono text-[11px] text-monitor-muted">Syncing reel…</p>
      )}
    </div>
  );
}

export function clipReelToDrafts(files: File[]): LocalClipDraft[] {
  return files.map((file, index) => ({
    id: `clip_${index}`,
    file,
    order: index,
    included: true,
    role: index === 0 ? "hook" : "clip",
    cropStartS: null,
    cropEndS: null,
    durationS: null,
    previewUrl: URL.createObjectURL(file),
  }));
}

export function reelResponseToClipInfo(response: ClipReelResponse): ClipInfo[] {
  return response.clips.map((clip) => ({
    ...clip,
    cropStartS: clip.crop_start_s,
    cropEndS: clip.crop_end_s,
    durationS: clip.duration_s,
  }));
}