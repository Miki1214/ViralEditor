import { useId, type ReactNode } from "react";

export type FormState = {
  projectName: string;
  hookText: string;
  emphasisWords: string;
  fillColor: string;
  emphasisColor: string;
  fontFamily: string;
  safePaddingPct: number;
  targetDurationS: number;
  useFullTrack: boolean;
};

interface JobFormProps {
  projectName: string;
  onProjectNameChange: (value: string) => void;
  onAudioSelected: (file: File) => void;
  audioName: string | null;
  analyzing: boolean;
  disabled?: boolean;
  disabledReason?: string | null;
  audioScope?: ReactNode;
}

export function JobForm({
  projectName,
  onProjectNameChange,
  onAudioSelected,
  audioName,
  analyzing,
  disabled = false,
  disabledReason = null,
  audioScope = null,
}: JobFormProps) {
  const audioInputId = useId();
  const projectNameId = useId();

  return (
    <form
      id="job-form"
      className="panel space-y-6 p-5"
      onSubmit={(e) => e.preventDefault()}
    >
      <section id="job-form-section" className="space-y-3">
        <div>
          <label
            id="job-form-project-label"
            htmlFor={projectNameId}
            className="mb-1 block font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted"
          >
            Project name
          </label>
          <input
            id={projectNameId}
            type="text"
            className="field-input w-full"
            placeholder="My Vivaldi Short"
            value={projectName}
            disabled={analyzing}
            onChange={(e) => onProjectNameChange(e.target.value)}
          />
        </div>
        <div>
          <h2 id="job-form-music-title" className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Music
          </h2>
          <p id="job-form-music-desc" className="mt-1 text-xs text-monitor-muted">
            Drop your track — we analyze beats and suggest loop windows. Pick target
            length in the scope below once analysis finishes.
          </p>
        </div>
        <label htmlFor={audioInputId} id="job-form-audio-label" className="block">
          <div id="job-form-drop-zone" className="flex min-h-[72px] cursor-pointer flex-col items-center justify-center rounded border border-dashed border-monitor-border bg-monitor-bg/50 px-4 py-4 text-center transition hover:border-scope-dim">
            <input
              id={audioInputId}
              type="file"
              accept="audio/*"
              className="sr-only"
              disabled={disabled || analyzing}
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) onAudioSelected(file);
                e.target.value = "";
              }}
            />
            <span id="job-form-drop-text" className="text-xs text-monitor-muted">
              {audioName ?? "Drop music here or click to browse"}
            </span>
            {analyzing && (
              <span id="job-form-analyzing-text" className="mt-2 font-mono text-[11px] text-scope-trace">
                Analyzing audio…
              </span>
            )}
          </div>
        </label>
        {audioScope}
      </section>

      {disabledReason && (
        <p id="job-form-disabled-msg" className="text-xs text-hook-gold">{disabledReason}</p>
      )}
    </form>
  );
}
