import { BASS, DROP, LABEL_COLOR, TRACE } from "./scopeTheme";

export interface ScopeLegendItem {
  id: string;
  color: string;
  label: string;
  description: string;
  kind: "line" | "block" | "tick" | "ribbon";
  borderColor?: string;
}

export const AUDIO_SCOPE_LEGEND: ScopeLegendItem[] = [
  {
    id: "waveform",
    color: TRACE,
    label: "Waveform",
    description: "Onset energy envelope",
    kind: "line",
  },
  {
    id: "block",
    color: "rgba(244,196,48,0.35)",
    borderColor: DROP,
    label: "Loop block",
    description: "Suggested edit window",
    kind: "block",
  },
  {
    id: "section",
    color: "rgba(56,189,248,0.35)",
    label: "Section",
    description: "Structure segment · extra rows when overlapping",
    kind: "ribbon",
  },
  {
    id: "drop",
    color: DROP,
    label: "Drop",
    description: "Loud hit · zoom cue",
    kind: "tick",
  },
  {
    id: "bass",
    color: BASS,
    label: "Bass",
    description: "Low accent · rotate cue",
    kind: "tick",
  },
  {
    id: "bar",
    color: LABEL_COLOR,
    label: "Bar",
    description: "Gray tick · measure downbeat in marker strip",
    kind: "tick",
  },
];

function LegendSwatch({ item }: { item: ScopeLegendItem }) {
  if (item.kind === "line") {
    return (
      <span
        className="inline-block h-0.5 w-4 shrink-0 rounded-full"
        style={{ backgroundColor: item.color }}
        aria-hidden
      />
    );
  }

  if (item.kind === "block") {
    return (
      <span
        className="inline-block h-3 w-4 shrink-0 rounded-sm border"
        style={{
          backgroundColor: item.color,
          borderColor: item.borderColor ?? item.color,
        }}
        aria-hidden
      />
    );
  }

  if (item.kind === "ribbon") {
    return (
      <span
        className="inline-block h-1.5 w-4 shrink-0 rounded-sm"
        style={{ backgroundColor: item.color }}
        aria-hidden
      />
    );
  }

  return (
    <span
      className="inline-block h-3.5 w-1 shrink-0 rounded-full"
      style={{ backgroundColor: item.color }}
      aria-hidden
    />
  );
}

interface ScopeLegendProps {
  items?: ScopeLegendItem[];
  /** Flush under the scope canvas / marker strip (no outer card border). */
  embedded?: boolean;
}

export function ScopeLegend({ items = AUDIO_SCOPE_LEGEND, embedded = false }: ScopeLegendProps) {
  return (
    <div
      className={
        embedded
          ? "flex flex-wrap items-start gap-x-5 gap-y-2 border-t border-monitor-border/60 bg-[#101214] px-3 py-2"
          : "flex flex-wrap items-start gap-x-5 gap-y-2 rounded border border-monitor-border/60 bg-[#101214] px-3 py-2"
      }
      aria-label="Scope legend"
    >
      {items.map((item) => (
        <div key={item.id} className="flex min-w-0 items-start gap-2">
          <span className="mt-0.5 flex h-3.5 w-4 shrink-0 items-center justify-center">
            <LegendSwatch item={item} />
          </span>
          <span className="min-w-0 leading-tight">
            <span className="font-mono text-[10px] uppercase tracking-wide text-scope-trace">
              {item.label}
            </span>
            <span className="font-mono text-[10px] text-monitor-muted"> · {item.description}</span>
          </span>
        </div>
      ))}
    </div>
  );
}
