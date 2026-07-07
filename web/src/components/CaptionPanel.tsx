import { useCallback, useEffect, useMemo, useState } from "react";
import { CAPTION_STYLE_PRESETS } from "../constants/captionPresets";
import { HOOK_FONT_OPTIONS } from "../constants/fonts";
import { WHISPER_LANGUAGE_OPTIONS } from "../constants/whisperLanguages";
import type {
  CaptionChunkPayload,
  CaptionPayload,
  CaptionPatchInput,
  TranscribeOptions,
  TranscribeSource,
} from "../types";
import type { FormState } from "./JobForm";
import { CaptionWordTimeline } from "./CaptionWordTimeline";

interface CaptionPanelProps {
  form: FormState;
  caption: CaptionPayload | null;
  selectedSlotId: string | null;
  saving?: boolean;
  transcribing?: boolean;
  onPatchForm: (partial: Partial<FormState>) => void;
  onPatchCaption: (payload: CaptionPatchInput) => Promise<CaptionPayload>;
  onTranscribe: (source: TranscribeSource, options: TranscribeOptions, file?: File) => Promise<void>;
}

function chunksToWordTiming(chunks: CaptionChunkPayload[]) {
  return chunks.flatMap((chunk) =>
    chunk.words.map((word) => ({
      text: word.text,
      start_s: word.start_s,
      end_s: word.end_s,
    })),
  );
}

function StyleFields({
  idPrefix,
  style,
  onChange,
}: {
  idPrefix: string;
  style: CaptionPayload["caption_style"];
  onChange: (partial: CaptionPatchInput["caption_style"]) => void;
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-2">
      <label className="block sm:col-span-2">
        <span className="field-label">Font</span>
        <select
          id={`${idPrefix}-font-select`}
          className="field-select mt-1 w-full"
          value={style.font_family}
          onChange={(e) => onChange({ font_family: e.target.value })}
        >
          {HOOK_FONT_OPTIONS.map((font) => (
            <option key={font.value} value={font.value}>
              {font.label}
            </option>
          ))}
        </select>
      </label>
      <label className="block">
        <span className="field-label">Fill</span>
        <input
          type="color"
          className="field-color"
          value={style.fill_color}
          onChange={(e) => onChange({ fill_color: e.target.value })}
        />
      </label>
      <label className="block">
        <span className="field-label">Emphasis</span>
        <input
          type="color"
          className="field-color"
          value={style.emphasis_color}
          onChange={(e) => onChange({ emphasis_color: e.target.value })}
        />
      </label>
      <label className="block">
        <span className="field-label">Outline</span>
        <input
          type="color"
          className="field-color"
          value={style.outline_color}
          onChange={(e) => onChange({ outline_color: e.target.value })}
        />
      </label>
      <label className="flex items-center gap-2 pt-5">
        <input
          type="checkbox"
          checked={style.outline_enabled}
          onChange={(e) => onChange({ outline_enabled: e.target.checked })}
        />
        <span className="text-xs text-monitor-muted">Outline</span>
      </label>
      <label className="flex items-center gap-2 pt-5">
        <input
          type="checkbox"
          checked={style.box_enabled}
          onChange={(e) => onChange({ box_enabled: e.target.checked })}
        />
        <span className="text-xs text-monitor-muted">Background box</span>
      </label>
      <label className="block sm:col-span-2">
        <span className="field-label">Position</span>
        <div className="mt-1 flex gap-2">
          {(["top", "center", "bottom"] as const).map((pos) => (
            <button
              key={pos}
              type="button"
              className={`btn-ghost px-2 py-1 font-mono text-[10px] uppercase ${
                style.position === pos ? "text-scope-trace" : ""
              }`}
              onClick={() => onChange({ position: pos })}
            >
              {pos}
            </button>
          ))}
        </div>
      </label>
      <label className="block">
        <span className="field-label">Safe padding %</span>
        <input
          type="number"
          min={0}
          max={50}
          className="field-input mt-1"
          value={style.safe_padding_pct}
          onChange={(e) => onChange({ safe_padding_pct: Number(e.target.value) || 10 })}
        />
      </label>
    </div>
  );
}

export function CaptionPanel({
  form,
  caption,
  selectedSlotId,
  saving = false,
  transcribing = false,
  onPatchForm,
  onPatchCaption,
  onTranscribe,
}: CaptionPanelProps) {
  const [timingSlotId, setTimingSlotId] = useState<string | null>(null);
  const [slotDrafts, setSlotDrafts] = useState<Record<string, string>>({});
  const [transcribeSource, setTranscribeSource] = useState<TranscribeSource>("audio_track");
  const [customMediaFile, setCustomMediaFile] = useState<File | null>(null);
  const [transcribeLanguage, setTranscribeLanguage] = useState("auto");
  const [transcribeTranslate, setTranscribeTranslate] = useState(false);
  const [scriptDraft, setScriptDraft] = useState(caption?.script_text ?? "");
  const [captionAction, setCaptionAction] = useState<"cleanup" | "allocate" | "sync" | null>(
    null,
  );

  useEffect(() => {
    if (caption) {
      setScriptDraft(caption.script_text);
      setSlotDrafts(caption.slot_overrides);
    }
  }, [caption]);

  const handleWordTextChange = useCallback(
    async (
      slotId: string,
      chunks: CaptionChunkPayload[],
      wordIndex: number,
      newText: string,
    ) => {
      if (!caption) return;
      const timing = chunksToWordTiming(chunks);
      timing[wordIndex] = { ...timing[wordIndex], text: newText };
      await onPatchCaption({
        word_timing_overrides: { [slotId]: timing },
        slot_overrides: {
          ...caption.slot_overrides,
          [slotId]: timing.map((word) => word.text).join(" "),
        },
      });
    },
    [caption, onPatchCaption],
  );

  const handleCleanup = useCallback(async () => {
    if (!caption) return;
    setCaptionAction("cleanup");
    try {
      await onPatchCaption({
        script_text: scriptDraft,
        slot_overrides: caption.slot_overrides,
        cleanup: true,
      });
    } finally {
      setCaptionAction(null);
    }
  }, [caption, onPatchCaption, scriptDraft]);

  const handleAutoAllocate = useCallback(async () => {
    setCaptionAction("allocate");
    try {
      await onPatchCaption({ script_text: scriptDraft, auto_allocate: true });
    } finally {
      setCaptionAction(null);
    }
  }, [onPatchCaption, scriptDraft]);

  const handleAudioSync = useCallback(async () => {
    setCaptionAction("sync");
    try {
      await onPatchCaption({ audio_sync: true });
    } finally {
      setCaptionAction(null);
    }
  }, [onPatchCaption]);

  const wpsOptions = useMemo(
    () => caption?.wps_presets ?? [{ words_per_second: 5, label: "Recommended" }],
    [caption?.wps_presets],
  );

  const applyPreset = useCallback(
    (presetId: string) => {
      const preset = CAPTION_STYLE_PRESETS.find((item) => item.id === presetId);
      if (!preset) return;
      void onPatchCaption({
        hook_style: preset.hook,
        caption_style: preset.body,
      });
    },
    [onPatchCaption],
  );

  const selectedBudget = caption?.slot_budgets.find(
    (slot) => slot.slot_id === (timingSlotId ?? selectedSlotId),
  );

  return (
    <div id="caption-panel" className="panel space-y-5 p-5">
      <div>
        <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
          Captions & overlay
        </h2>
        <p className="mt-1 text-xs text-monitor-muted">
          Title on the hook slot; body captions split across storyboard clips by reading speed.
        </p>
      </div>

      <section className="space-y-3 rounded border border-monitor-border bg-monitor-bg/30 p-4">
        <h3 className="font-mono text-[10px] uppercase tracking-[0.18em] text-hook-gold">Title</h3>
        <label className="block">
          <span className="field-label">Hook title</span>
          <input
            className="field-input mt-1 w-full"
            value={form.hookText}
            onChange={(e) => onPatchForm({ hookText: e.target.value })}
            onBlur={() =>
              void onPatchCaption({
                hook_text: form.hookText,
                emphasis_words: form.emphasisWords
                  .split(",")
                  .map((w) => w.trim())
                  .filter(Boolean),
              })
            }
          />
        </label>
        <label className="block">
          <span className="field-label">Emphasis words</span>
          <input
            className="field-input mt-1 w-full"
            value={form.emphasisWords}
            placeholder="30, days"
            onChange={(e) => onPatchForm({ emphasisWords: e.target.value })}
            onBlur={() =>
              void onPatchCaption({
                emphasis_words: form.emphasisWords
                  .split(",")
                  .map((w) => w.trim())
                  .filter(Boolean),
              })
            }
          />
        </label>
        {caption && (
          <StyleFields
            idPrefix="hook-style"
            style={caption.hook_style}
            onChange={(partial) => void onPatchCaption({ hook_style: partial })}
          />
        )}
      </section>

      <section className="space-y-3 rounded border border-monitor-border bg-monitor-bg/30 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h3 className="font-mono text-[10px] uppercase tracking-[0.18em] text-scope-trace">
            Body captions
          </h3>
          <div className="flex flex-wrap items-center gap-2">
            <select
              className="field-select font-mono text-[10px]"
              value={transcribeSource}
              disabled={transcribing || saving}
              onChange={(e) => {
                const next = e.target.value as TranscribeSource;
                setTranscribeSource(next);
                if (next !== "custom") {
                  setCustomMediaFile(null);
                }
              }}
            >
              <option value="audio_track">Transcribe from Audio Track</option>
              <option value="clips">Transcribe from Clips</option>
              <option value="custom">Transcribe from Custom Upload</option>
            </select>
            <button
              type="button"
              className="btn-ghost font-mono text-[10px]"
              disabled={
                transcribing ||
                saving ||
                !caption?.transcribe_available ||
                (transcribeSource === "custom" && !customMediaFile)
              }
              title={
                caption?.transcribe_available
                  ? "Transcribe audio into caption script"
                  : "Install faster-whisper on the server to enable"
              }
              onClick={() =>
                void onTranscribe(
                  transcribeSource,
                  {
                    language: transcribeLanguage,
                    translate: transcribeTranslate,
                  },
                  transcribeSource === "custom" ? customMediaFile ?? undefined : undefined,
                )
              }
            >
              {transcribing ? "Transcribing…" : "Auto-transcribe"}
            </button>
          </div>
        </div>

        {transcribeSource === "custom" && (
          <label className="block">
            <span className="field-label">Custom audio or video</span>
            <input
              type="file"
              accept="audio/*,video/*"
              className="field-input mt-1 w-full text-xs"
              disabled={transcribing || saving}
              onChange={(e) => setCustomMediaFile(e.target.files?.[0] ?? null)}
            />
          </label>
        )}

        <div className="flex flex-wrap items-end gap-3">
          <label className="block min-w-[10rem] flex-1">
            <span className="field-label">Transcribe language</span>
            <select
              className="field-select mt-1 w-full font-mono text-[10px]"
              value={transcribeLanguage}
              disabled={transcribing || saving}
              onChange={(e) => setTranscribeLanguage(e.target.value)}
            >
              {WHISPER_LANGUAGE_OPTIONS.map((option) => (
                <option key={option.code} value={option.code}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2 pb-1">
            <input
              type="checkbox"
              checked={transcribeTranslate}
              disabled={transcribing || saving}
              onChange={(e) => setTranscribeTranslate(e.target.checked)}
            />
            <span className="text-xs text-monitor-muted">Translate to English</span>
          </label>
        </div>

        <label className="block">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <span className="field-label">Script</span>
            <div className="flex flex-wrap gap-1">
              <button
                type="button"
                className="btn-ghost px-2 py-1 font-mono text-[10px] uppercase"
                disabled={captionAction !== null || saving || !scriptDraft.trim()}
                title="Normalize script and per-clip caption text (quotes, whitespace, punctuation spacing)"
                onClick={() => void handleCleanup()}
              >
                {captionAction === "cleanup" ? "Cleaning…" : "Clean up"}
              </button>
              <button
                type="button"
                className="btn-ghost px-2 py-1 font-mono text-[10px] uppercase text-scope-trace"
                disabled={captionAction !== null || saving || !scriptDraft.trim()}
                title="Split the script across clips by reading-speed word budget (even text spread)"
                onClick={() => void handleAutoAllocate()}
              >
                {captionAction === "allocate" ? "Allocating…" : "Auto-allocate"}
              </button>
              <button
                type="button"
                className="btn-ghost px-2 py-1 font-mono text-[10px] uppercase text-hook-gold"
                disabled={
                  captionAction !== null ||
                  saving ||
                  !caption?.audio_sync_available
                }
                title={
                  caption?.audio_sync_available
                    ? "Re-assign clip captions using stored ASR word timestamps from transcription"
                    : "Run Auto-transcribe first to store ASR timing"
                }
                onClick={() => void handleAudioSync()}
              >
                {captionAction === "sync" ? "Syncing…" : "Audio-sync captions"}
              </button>
            </div>
          </div>
          <textarea
            className="field-input mt-1 min-h-[96px] w-full resize-y"
            value={scriptDraft}
            placeholder="Write your full caption script here…"
            onChange={(e) => setScriptDraft(e.target.value)}
            onBlur={(e) => {
              if (e.target.value === caption?.script_text) return;
              void onPatchCaption({ script_text: e.target.value });
            }}
          />
          <p className="mt-1 text-[10px] text-monitor-muted">
            Editing saves raw text only. Use Clean up to normalize, Auto-allocate to spread by
            reading speed, or Audio-sync to restore transcription timing.
          </p>
        </label>

        <label className="block">
          <span className="field-label">Reading speed</span>
          <select
            className="field-select mt-1 w-full"
            value={caption?.words_per_second ?? 5}
            onChange={(e) =>
              void onPatchCaption({ words_per_second: Number(e.target.value) })
            }
          >
            {wpsOptions.map((preset) => (
              <option key={preset.words_per_second} value={preset.words_per_second}>
                {preset.words_per_second} words/sec — {preset.label}
                {preset.label === "Recommended" ? " (based on viral caption pacing)" : ""}
              </option>
            ))}
          </select>
        </label>

        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={caption?.caption_style.karaoke_enabled ?? true}
            onChange={(e) => void onPatchCaption({ karaoke_enabled: e.target.checked })}
          />
          <span className="text-xs text-monitor-muted">Karaoke word highlight</span>
        </label>

        <div className="flex flex-wrap gap-2">
          {CAPTION_STYLE_PRESETS.map((preset) => (
            <button
              key={preset.id}
              type="button"
              className="btn-ghost px-2 py-1 font-mono text-[10px]"
              onClick={() => applyPreset(preset.id)}
            >
              {preset.label}
            </button>
          ))}
        </div>

        {caption && (
          <StyleFields
            idPrefix="caption-style"
            style={caption.caption_style}
            onChange={(partial) => void onPatchCaption({ caption_style: partial })}
          />
        )}
      </section>

      {caption && caption.slot_budgets.length > 0 && (
        <section className="space-y-2">
          <h3 className="font-mono text-[10px] uppercase tracking-[0.18em] text-monitor-muted">
            Per-clip budgets
          </h3>
          <div className="space-y-2">
            {caption.slot_budgets.map((slot) => {
              const over = slot.actual_words > slot.suggested_words;
              const under =
                slot.actual_words < slot.suggested_words && slot.suggested_words > 0;
              const overrideText = slotDrafts[slot.slot_id] ?? caption.slot_overrides[slot.slot_id] ?? "";
              return (
                <div
                  key={slot.slot_id}
                  className={`rounded border p-3 ${
                    selectedSlotId === slot.slot_id
                      ? "border-scope-trace bg-scope-trace/5"
                      : "border-monitor-border"
                  }`}
                >
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <p className="font-mono text-[11px] text-monitor-text">
                      {slot.label} · {slot.duration_s.toFixed(1)}s
                    </p>
                    <p
                      className={`font-mono text-[10px] ${
                        over ? "text-hook-gold" : under ? "text-monitor-muted" : "text-scope-trace"
                      }`}
                    >
                      {slot.actual_words}/{slot.suggested_words} words
                    </p>
                  </div>
                  {slot.has_asr_timing ? (
                    slot.chunks.length > 0 && (
                      <div className="mt-2">
                        <CaptionWordTimeline
                          slotLabel={slot.label}
                          durationS={slot.duration_s}
                          chunks={slot.chunks}
                          editable
                          hasAsrTiming
                          onWordTextChange={(wordIndex, newText) =>
                            void handleWordTextChange(slot.slot_id, slot.chunks, wordIndex, newText)
                          }
                        />
                      </div>
                    )
                  ) : (
                    <>
                      <textarea
                        className="field-input mt-2 min-h-[48px] w-full text-xs"
                        placeholder="Override text for this clip (optional)"
                        value={overrideText}
                        onChange={(e) =>
                          setSlotDrafts((current) => ({
                            ...current,
                            [slot.slot_id]: e.target.value,
                          }))
                        }
                        onBlur={(e) => {
                          const nextValue = e.target.value;
                          if (nextValue === (caption.slot_overrides[slot.slot_id] ?? "")) return;
                          void onPatchCaption({
                            slot_overrides: {
                              ...caption.slot_overrides,
                              [slot.slot_id]: nextValue,
                            },
                          });
                        }}
                      />
                      {slot.chunks.length > 0 && (
                        <button
                          type="button"
                          className="btn-ghost mt-2 font-mono text-[10px]"
                          onClick={() =>
                            setTimingSlotId((current) =>
                              current === slot.slot_id ? null : slot.slot_id,
                            )
                          }
                        >
                          {timingSlotId === slot.slot_id ? "Hide timing" : "Fine-tune timing"}
                        </button>
                      )}
                    </>
                  )}
                </div>
              );
            })}
          </div>
        </section>
      )}

      {selectedBudget &&
        timingSlotId === selectedBudget.slot_id &&
        !selectedBudget.has_asr_timing && (
        <CaptionWordTimeline
          slotLabel={selectedBudget.label}
          durationS={selectedBudget.duration_s}
          chunks={selectedBudget.chunks}
        />
      )}

      {saving && (
        <p className="font-mono text-[11px] text-monitor-muted">Syncing captions…</p>
      )}
    </div>
  );
}
