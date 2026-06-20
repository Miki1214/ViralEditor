export type DebugLevel = "info" | "warn" | "error";

export interface DebugLogEntry {
  id: string;
  ts: number;
  level: DebugLevel;
  source: string;
  message: string;
  detail?: string;
}

const MAX_ENTRIES = 200;

let entries: DebugLogEntry[] = [];
const listeners = new Set<() => void>();

/** Original console methods — used by pushDebugLog so capture hooks don't recurse */
let originalInfo: typeof console.info | null = null;
let originalWarn: typeof console.warn | null = null;
let originalError: typeof console.error | null = null;

function writeToConsole(
  level: DebugLevel,
  source: string,
  message: string,
  detail?: string,
): void {
  const prefix = `[debug:${source}]`;
  const args = detail ? [prefix, message, detail] : [prefix, message];
  if (level === "error") {
    (originalError ?? console.error).apply(console, args);
  } else if (level === "warn") {
    (originalWarn ?? console.warn).apply(console, args);
  } else {
    (originalInfo ?? console.info).apply(console, args);
  }
}

function isOwnDebugMessage(args: unknown[]): boolean {
  return args.some(
    (arg) => typeof arg === "string" && arg.startsWith("[debug:"),
  );
}

function notify() {
  for (const listener of listeners) {
    listener();
  }
}

export function isDebugMode(): boolean {
  return (
    typeof window !== "undefined" &&
    new URLSearchParams(window.location.search).get("debug") === "1"
  );
}

export function pushDebugLog(
  level: DebugLevel,
  source: string,
  message: string,
  detail?: string,
): void {
  const entry: DebugLogEntry = {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    ts: Date.now(),
    level,
    source,
    message,
    detail,
  };
  entries = [entry, ...entries].slice(0, MAX_ENTRIES);
  notify();
  writeToConsole(level, source, message, detail);
}

export function getDebugLogs(): DebugLogEntry[] {
  return entries;
}

export function clearDebugLogs(): void {
  entries = [];
  notify();
}

export function subscribeDebugLogs(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function installDebugConsoleCapture(): () => void {
  if (!isDebugMode()) {
    return () => undefined;
  }

  originalInfo = console.info.bind(console);
  originalWarn = console.warn.bind(console);
  originalError = console.error.bind(console);

  console.warn = (...args: unknown[]) => {
    if (!isOwnDebugMessage(args)) {
      pushDebugLog("warn", "console", args.map(String).join(" "));
    }
    originalWarn!(...args);
  };

  console.error = (...args: unknown[]) => {
    if (!isOwnDebugMessage(args)) {
      pushDebugLog("error", "console", args.map(String).join(" "));
    }
    originalError!(...args);
  };

  const onWindowError = (event: ErrorEvent) => {
    pushDebugLog(
      "error",
      "window",
      event.message,
      event.filename ? `${event.filename}:${event.lineno}:${event.colno}` : undefined,
    );
  };

  const onUnhandledRejection = (event: PromiseRejectionEvent) => {
    const reason = event.reason;
    const detail =
      reason instanceof Error
        ? reason.stack ?? reason.message
        : typeof reason === "string"
          ? reason
          : JSON.stringify(reason);
    pushDebugLog("error", "unhandled", "Unhandled promise rejection", detail);
  };

  window.addEventListener("error", onWindowError);
  window.addEventListener("unhandledrejection", onUnhandledRejection);

  return () => {
    if (originalInfo) console.info = originalInfo;
    if (originalWarn) console.warn = originalWarn;
    if (originalError) console.error = originalError;
    originalInfo = null;
    originalWarn = null;
    originalError = null;
    window.removeEventListener("error", onWindowError);
    window.removeEventListener("unhandledrejection", onUnhandledRejection);
  };
}
