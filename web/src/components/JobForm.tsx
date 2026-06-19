import { useId, useRef } from "react";
import { DEFAULT_HOOK_FONT, HOOK_FONT_OPTIONS } from "../constants/fonts";
import type { LocalClipDraft } from "./ClipReelPanel";

type FormState = {
  hookText: string;
  emphasisWords: string;
  fillColor: string;
  emphasisColor: string;
  fontFamily: string;
  safePaddingPct: number;
  targetDurationS: number;
  useFullTrack: boolean;
  audio: File | null;
  localClips: LocalClipDraft[];
};

interface JobFormProps {
  form: FormState;
  onPatch: (partial: Partial<FormState>) => void;
  onLocalClipsChange: (update: ClipsUpdater) => void;
  onSubmit: () => void;
  submitting: boolean;
  disabled?: boolean;
  disabledReason?: string | null;
}

type ClipsUpdater = import("../hooks/useLocalClipDrafts").LocalClipsUpdater;

function isVideoFile(file: File): boolean {
  if (file.type.startsWith("video/")) return true;
  return /\.(mp4|mov|webm|mkv|avi|m4v)$/i.test(file.name);
}

function MultiVideoField({
  clips,
  onClips,
}: {
  clips: LocalClipDraft[];
  onClips: (update: ClipsUpdater) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const inputId = useId();

  const addFiles = (files: FileList | File[] | null) => {
    if (!files?.length) return;
    const picked = Array.from(files).filter(isVideoFile);
    if (picked.length === 0) return;

    onClips((current) => {
      const startOrder = current.length;
      const added: LocalClipDraft[] = picked.map((file, offset) => ({
        id: `clip_${startOrder + offset}`,
        file,
        order: startOrder + offset,
        included: true,
        role: startOrder + offset === 0 && current.length === 0 ? "hook" : "clip",
        cropStartS: null,
        cropEndS: null,
        durationS: null,
        previewUrl: URL.createObjectURL(file),
      }));
      return [...current, ...added];
    });
  };

  return (
    <div className="block sm:col-span-2">
      <span className="field-label">Timelapse clips (multi-drop)</span>
      <label
        htmlFor={inputId}
        className="mt-1 flex min-h-[88px] cursor-pointer flex-col items-center justify-center rounded border border-dashed border-monitor-border bg-monitor-bg/50 px-4 py-5 text-center transition hover:border-scope-dim"
        onDragEnter={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        onDragOver={(e) => {
          e.preventDefault();
          e.stopPropagation();
          e.dataTransfer.dropEffect = "copy";
        }}
        onDrop={(e) => {
          e.preventDefault();
          e.stopPropagation();
          addFiles(e.dataTransfer.files);
        }}
      >
        <input
          ref={inputRef}
          id={inputId}
          type="file"
          accept="video/*,.mp4,.mov,.webm,.mkv,.avi,.m4v"
          multiple
          className="sr-only"
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = "";
          }}
        />
        <span className="pointer-events-none text-xs text-monitor-muted">
          Drop clips here or click to browse
        </span>
        {clips.length > 0 && (
          <p className="pointer-events-none mt-2 font-mono text-[11px] text-scope-trace">
            {clips.length} clip{clips.length === 1 ? "" : "s"} queued
          </p>
        )}
      </label>
      {clips.length > 0 && (
        <ul className="mt-2 space-y-1">
          {clips.map((clip) => (
            <li
              key={clip.id}
              className="truncate rounded border border-monitor-border bg-monitor-bg px-2 py-1 font-mono text-[11px] text-monitor-muted"
            >
              {clip.file.name}
              {clip.role === "hook" ? " · hook" : ""}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function AudioField({
  file,
  onFile,
}: {
  file: File | null;
  onFile: (file: File | null) => void;
}) {
  return (
    <label className="block">
      <span className="field-label">Music track</span>
      <input
        type="file"
        accept="audio/*"
        className="field-input cursor-pointer file:mr-3 file:rounded file:border-0 file:bg-monitor-border file:px-2 file:py-1 file:text-xs file:text-monitor-text"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
      {file && (
        <p className="mt-1 truncate font-mono text-[11px] text-monitor-muted">{file.name}</p>
      )}
    </label>
  );
}

const TARGET_PRESETS = [15, 30, 45, 60] as const;

export function JobForm({
  form,
  onPatch,
  onLocalClipsChange,
  onSubmit,
  submitting,
  disabled,
  disabledReason,
}: JobFormProps) {
  const missingAssets = form.localClips.length === 0 || !form.audio;

  return (
    <form
      className="panel space-y-5 p-5"
      onSubmit={(e) => {
        e.preventDefault();
        onSubmit();
      }}
    >
      <div>
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
          Assets
        </h2>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <MultiVideoField clips={form.localClips} onClips={onLocalClipsChange} />
          <AudioField file={form.audio} onFile={(audio) => onPatch({ audio })} />
        </div>
      </div>

      <div>
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
          Hook
        </h2>
        <div className="mt-3 grid gap-4">
          <label className="block">
            <span className="field-label">Headline</span>
            <input
              className="field-input"
              value={form.hookText}
              onChange={(e) => onPatch({ hookText: e.target.value })}
              required
            />
          </label>
          <label className="block">
            <span className="field-label">Emphasis words (comma-separated)</span>
            <input
              className="field-input font-mono text-xs"
              value={form.emphasisWords}
              onChange={(e) => onPatch({ emphasisWords: e.target.value })}
            />
          </label>
        </div>
      </div>

      <div>
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
          Style
        </h2>
        <div className="mt-3 grid gap-4 sm:grid-cols-2">
          <label className="block">
            <span className="field-label">Fill color</span>
            <input
              type="color"
              className="h-10 w-full cursor-pointer rounded border border-monitor-border bg-monitor-bg"
              value={form.fillColor}
              onChange={(e) => onPatch({ fillColor: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="field-label">Emphasis color</span>
            <input
              type="color"
              className="h-10 w-full cursor-pointer rounded border border-monitor-border bg-monitor-bg"
              value={form.emphasisColor}
              onChange={(e) => onPatch({ emphasisColor: e.target.value })}
            />
          </label>
          <label className="block sm:col-span-2">
            <span className="field-label">Font</span>
            <select
              className="field-select"
              value={
                HOOK_FONT_OPTIONS.some((f) => f.value === form.fontFamily)
                  ? form.fontFamily
                  : DEFAULT_HOOK_FONT
              }
              onChange={(e) => onPatch({ fontFamily: e.target.value })}
            >
              {HOOK_FONT_OPTIONS.map((font) => (
                <option key={font.value} value={font.value}>
                  {font.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block sm:col-span-2">
            <span className="field-label">Safe padding ({form.safePaddingPct}%)</span>
            <input
              type="range"
              min={5}
              max={20}
              value={form.safePaddingPct}
              onChange={(e) => onPatch({ safePaddingPct: Number(e.target.value) })}
              className="w-full accent-scope-trace"
            />
          </label>
        </div>
      </div>

      <div>
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
          Music window
        </h2>
        <p className="mt-1 text-xs text-monitor-muted">
          Target short length for long tracks — analysis will suggest the best blocks.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          {TARGET_PRESETS.map((seconds) => (
            <button
              key={seconds}
              type="button"
              className={`rounded border px-2.5 py-1 font-mono text-xs transition ${
                !form.useFullTrack && form.targetDurationS === seconds
                  ? "border-hook-gold bg-hook-gold/15 text-hook-gold"
                  : "border-monitor-border text-monitor-muted hover:border-scope-dim"
              }`}
              onClick={() => onPatch({ targetDurationS: seconds, useFullTrack: false })}
            >
              {seconds}s
            </button>
          ))}
          <button
            type="button"
            className={`rounded border px-2.5 py-1 font-mono text-xs transition ${
              form.useFullTrack
                ? "border-hook-gold bg-hook-gold/15 text-hook-gold"
                : "border-monitor-border text-monitor-muted hover:border-scope-dim"
            }`}
            onClick={() => onPatch({ useFullTrack: true })}
          >
            Full track
          </button>
        </div>
      </div>

      <button
        type="submit"
        className="btn-primary w-full"
        disabled={submitting || disabled || missingAssets}
      >
        {submitting ? "Running pipeline…" : "Render"}
      </button>
      {(disabledReason || missingAssets) && !submitting && (
        <p className="text-center text-xs text-hook-gold" role="status">
          {missingAssets
            ? "Add at least one clip and a music track to enable Render."
            : disabledReason}
        </p>
      )}
    </form>
  );
}

export type { FormState };
