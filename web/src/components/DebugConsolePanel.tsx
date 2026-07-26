import { useEffect, useState } from "react";
import {
  clearDebugLogs,
  getDebugLogs,
  subscribeDebugLogs,
  type DebugLogEntry,
} from "../utils/debugLog";

function formatTime(ts: number): string {
  return new Date(ts).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function levelClass(level: DebugLogEntry["level"]): string {
  if (level === "error") return "text-red-400";
  if (level === "warn") return "text-amber-400";
  return "text-monitor-muted";
}

export function DebugConsolePanel() {
  const [entries, setEntries] = useState<DebugLogEntry[]>(() => getDebugLogs());
  const [open, setOpen] = useState(true);

  useEffect(() => subscribeDebugLogs(() => setEntries(getDebugLogs())), []);

  if (!open) {
    return (
      <button
        id="debug-console-show-btn"
        type="button"
        className="w-full font-mono text-[10px] text-scope-dim hover:text-monitor-text"
        onClick={() => setOpen(true)}
      >
        Show debug log ({entries.length})
      </button>
    );
  }

  return (
    <div id="debug-console-panel" className="w-full space-y-2 rounded border border-amber-700/40 bg-amber-950/15 p-3">
      <div className="flex items-center justify-between gap-2">
        <p id="debug-console-title" className="font-mono text-[10px] uppercase tracking-[0.14em] text-amber-400/90">
          Debug log
        </p>
        <div className="flex items-center gap-2">
          <button
            id="debug-console-clear-btn"
            type="button"
            className="font-mono text-[10px] text-monitor-muted hover:text-monitor-text"
            onClick={() => clearDebugLogs()}
          >
            Clear
          </button>
          <button
            id="debug-console-hide-btn"
            type="button"
            className="font-mono text-[10px] text-monitor-muted hover:text-monitor-text"
            onClick={() => setOpen(false)}
          >
            Hide
          </button>
        </div>
      </div>
      <div id="debug-console-log-list" className="max-h-48 space-y-1.5 overflow-y-auto font-mono text-[10px]">
        {entries.length === 0 ? (
          <p id="debug-console-no-entries" className="text-monitor-muted">No entries yet.</p>
        ) : (
          entries.map((entry) => (
            <div key={entry.id} id={`debug-console-entry-${entry.id}`} className="rounded border border-monitor-border/40 px-2 py-1">
              <p id={`debug-console-entry-msg-${entry.id}`} className={levelClass(entry.level)}>
                <span className="text-monitor-muted">{formatTime(entry.ts)}</span>
                {" · "}
                <span className="uppercase">{entry.source}</span>
                {" · "}
                {entry.message}
              </p>
              {entry.detail ? (
                <p id={`debug-console-entry-detail-${entry.id}`} className="mt-0.5 whitespace-pre-wrap break-words text-monitor-muted">
                  {entry.detail}
                </p>
              ) : null}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
