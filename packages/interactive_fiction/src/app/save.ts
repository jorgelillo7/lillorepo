/** Per-reader progress in localStorage. Every access is guarded: storage can be missing or full. */

import type { Vars } from "../engine/runtime.ts";

export interface Snapshot {
  passage: string;
  /** State *before* the passage rendered, so resuming never re-applies its (set:)s. */
  vars: Vars;
}

export interface Progress extends Snapshot {
  undo: Snapshot[];
  finished: boolean;
  /** The chapter's end code, once finished. */
  code?: string;
}

const PREFIX = "if:v1:";
const MAX_UNDO = 50;

const key = (series: string, chapter: string) => `${PREFIX}${series}:${chapter}`;

export function load(series: string, chapter: string): Progress | null {
  try {
    const raw = localStorage.getItem(key(series, chapter));
    return raw ? (JSON.parse(raw) as Progress) : null;
  } catch {
    return null;
  }
}

export function store(series: string, chapter: string, progress: Progress): void {
  try {
    progress.undo = progress.undo.slice(-MAX_UNDO);
    localStorage.setItem(key(series, chapter), JSON.stringify(progress));
  } catch {
    // Progress is a convenience; reading still works without it.
  }
}

export function clear(series: string, chapter: string): void {
  try {
    localStorage.removeItem(key(series, chapter));
  } catch {
    // Nothing to clear.
  }
}

const codesKey = (series: string) => `${PREFIX}${series}:codes`;

/** The end code each chapter last finished with. Kept apart from progress, so undo never loses it. */
export function loadCodes(series: string): Record<string, string> {
  try {
    const raw = localStorage.getItem(codesKey(series));
    return raw ? (JSON.parse(raw) as Record<string, string>) : {};
  } catch {
    return {};
  }
}

export function storeCode(series: string, chapter: string, code: string): void {
  try {
    localStorage.setItem(codesKey(series), JSON.stringify({ ...loadCodes(series), [chapter]: code }));
  } catch {
    // The reader can still type the code by hand.
  }
}
