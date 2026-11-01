/** Per-reader progress in localStorage. Every access is guarded: storage can be missing or full. */

import type { Vars } from "../engine/runtime.ts";

export interface Snapshot {
  passage: string;
  /** State *before* the passage rendered, so resuming never re-applies its (set:)s. */
  vars: Vars;
  /** The choice the reader made on this passage, once they left it. */
  choice?: string;
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

const MODE_KEY = `${PREFIX}mode`;

/** The reader's choice between point-and-click and plain text, for chapters that have scenes. */
export function loadMode(): "game" | "text" {
  try {
    return localStorage.getItem(MODE_KEY) === "text" ? "text" : "game";
  } catch {
    return "game";
  }
}

export function storeMode(mode: "game" | "text"): void {
  try {
    localStorage.setItem(MODE_KEY, mode);
  } catch {
    // The choice lasts until the page reloads.
  }
}

const LAST_KEY = `${PREFIX}last`;

/** The chapter read most recently, for "Continuar". */
export function lastPlayed(): { series: string; chapter: string } | null {
  try {
    const raw = localStorage.getItem(LAST_KEY);
    return raw ? (JSON.parse(raw) as { series: string; chapter: string }) : null;
  } catch {
    return null;
  }
}

export function storeLastPlayed(series: string, chapter: string): void {
  try {
    localStorage.setItem(LAST_KEY, JSON.stringify({ series, chapter }));
  } catch {
    // "Continuar" will simply not show.
  }
}

const foundKey = (series: string) => `${PREFIX}${series}:found`;

/** Every ending and passage the reader has ever reached, per chapter. Only grows; undo and restart keep it. */
export function loadFound(series: string): Record<string, { endings: string[]; passages: string[] }> {
  try {
    const raw = localStorage.getItem(foundKey(series));
    return raw ? JSON.parse(raw) : {};
  } catch {
    return {};
  }
}

export function recordFound(series: string, chapter: string, what: { ending?: string; passage?: string }): void {
  try {
    const all = loadFound(series);
    const mine = all[chapter] ?? { endings: [], passages: [] };
    if (what.ending && !mine.endings.includes(what.ending)) mine.endings.push(what.ending);
    if (what.passage && !mine.passages.includes(what.passage)) mine.passages.push(what.passage);
    all[chapter] = mine;
    localStorage.setItem(foundKey(series), JSON.stringify(all));
  } catch {
    // Discoveries are a bonus; reading goes on without them.
  }
}
