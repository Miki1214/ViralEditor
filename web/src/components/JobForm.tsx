import { DEFAULT_HOOK_FONT, HOOK_FONT_OPTIONS } from "../constants/fonts";

type FormState = {
  hookText: string;
  emphasisWords: string;
  fillColor: string;
  emphasisColor: string;
  fontFamily: string;
  safePaddingPct: number;
  video: File | null;
  audio: File | null;
};

interface JobFormProps {
  form: FormState;
  onChange: (next: FormState) => void;
  onSubmit: () => void;
  submitting: boolean;
  disabled?: boolean;
}

function FileField({
  label,
  accept,
  file,
  onFile,
}: {
  label: string;
  accept: string;
  file: File | null;
  onFile: (file: File | null) => void;
}) {
  return (
    <label className="block">
      <span className="field-label">{label}</span>
      <input
        type="file"
        accept={accept}
        className="field-input cursor-pointer file:mr-3 file:rounded file:border-0 file:bg-monitor-border file:px-2 file:py-1 file:text-xs file:text-monitor-text"
        onChange={(e) => onFile(e.target.files?.[0] ?? null)}
      />
      {file && (
        <p className="mt-1 truncate font-mono text-[11px] text-monitor-muted">
          {file.name}
        </p>
      )}
    </label>
  );
}

export function JobForm({
  form,
  onChange,
  onSubmit,
  submitting,
  disabled,
}: JobFormProps) {
  const patch = (partial: Partial<FormState>) => onChange({ ...form, ...partial });

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
          <FileField
            label="Timelapse video"
            accept="video/*"
            file={form.video}
            onFile={(video) => patch({ video })}
          />
          <FileField
            label="Music track"
            accept="audio/*"
            file={form.audio}
            onFile={(audio) => patch({ audio })}
          />
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
              onChange={(e) => patch({ hookText: e.target.value })}
              required
            />
          </label>
          <label className="block">
            <span className="field-label">Emphasis words (comma-separated)</span>
            <input
              className="field-input font-mono text-xs"
              value={form.emphasisWords}
              onChange={(e) => patch({ emphasisWords: e.target.value })}
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
              onChange={(e) => patch({ fillColor: e.target.value })}
            />
          </label>
          <label className="block">
            <span className="field-label">Emphasis color</span>
            <input
              type="color"
              className="h-10 w-full cursor-pointer rounded border border-monitor-border bg-monitor-bg"
              value={form.emphasisColor}
              onChange={(e) => patch({ emphasisColor: e.target.value })}
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
              onChange={(e) => patch({ fontFamily: e.target.value })}
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
              onChange={(e) => patch({ safePaddingPct: Number(e.target.value) })}
              className="w-full accent-scope-trace"
            />
          </label>
        </div>
      </div>

      <button type="submit" className="btn-primary w-full" disabled={submitting || disabled}>
        {submitting ? "Running pipeline…" : "Render"}
      </button>
    </form>
  );
}
