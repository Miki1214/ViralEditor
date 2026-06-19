import { useId, type ReactNode } from "react";

export type FormState = {
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
  onAudioSelected: (file: File) => void;
  audioName: string | null;
  analyzing: boolean;
  disabled?: boolean;
  disabledReason?: string | null;
  audioScope?: ReactNode;
}

export function JobForm({
  onAudioSelected,
  audioName,
  analyzing,
  disabled = false,
  disabledReason = null,
  audioScope = null,
}: JobFormProps) {
  const audioInputId = useId();

  return (
    <form
      className="panel space-y-6 p-5"
      onSubmit={(e) => e.preventDefault()}
    >
      <section className="space-y-3">
        <div>
          <h2 className="font-mono text-[10px] uppercase tracking-[0.2em] text-monitor-muted">
            Music
          </h2>
          <p className="mt-1 text-xs text-monitor-muted">
            Drop your track — we analyze beats and suggest loop windows. Pick target
            length in the scope below once analysis finishes.
          </p>
        </div>
        <label htmlFor={audioInputId} className="block">
          <div className="flex min-h-[72px] cursor-pointer flex-col items-center justify-center rounded border border-dashed border-monitor-border bg-monitor-bg/50 px-4 py-4 text-center transition hover:border-scope-dim">
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
            <span className="text-xs text-monitor-muted">
              {audioName ?? "Drop music here or click to browse"}
            </span>
            {analyzing && (
              <span className="mt-2 font-mono text-[11px] text-scope-trace">
                Analyzing audio…
              </span>
            )}
          </div>
        </label>
        {audioScope}
      </section>

      {disabledReason && (
        <p className="text-xs text-hook-gold">{disabledReason}</p>
      )}
    </form>
  );
}
