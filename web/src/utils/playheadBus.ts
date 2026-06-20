/** Imperative playhead updates for smooth transport without re-rendering heavy scope UI. */

export type PlayheadListener = (timeS: number) => void;

const listeners = new Set<PlayheadListener>();
let lastPlayheadS = 0;

export function subscribePlayhead(listener: PlayheadListener): () => void {
  listeners.add(listener);
  listener(lastPlayheadS);
  return () => listeners.delete(listener);
}

export function emitPlayheadUi(timeS: number): void {
  lastPlayheadS = timeS;
  for (const listener of listeners) {
    listener(timeS);
  }
}

export function getLastPlayheadS(): number {
  return lastPlayheadS;
}
