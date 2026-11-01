/** What the reader keeps between visits: progress per chapter, codes, discoveries, last chapter, mode. */

import type { Found } from "../engine/discoveries.ts";
import type { Progress } from "./progression.ts";
import { readJson, remove, writeJson } from "./storage.ts";

export function load(series: string, chapter: string): Progress | null {
  return readJson<Progress | null>(`${series}:${chapter}`, null);
}

export function store(series: string, chapter: string, progress: Progress): void {
  writeJson(`${series}:${chapter}`, progress);
}

export function clear(series: string, chapter: string): void {
  remove(`${series}:${chapter}`);
}

/** The end code each chapter last finished with. Kept apart from progress, so undo never loses it. */
export function loadCodes(series: string): Record<string, string> {
  return readJson(`${series}:codes`, {});
}

export function storeCode(series: string, chapter: string, code: string): void {
  writeJson(`${series}:codes`, { ...loadCodes(series), [chapter]: code });
}

/** The reader's choice between point-and-click and plain text, for chapters that have scenes. */
export function loadMode(): "game" | "text" {
  return readJson<string>("mode", "game") === "text" ? "text" : "game";
}

export function storeMode(mode: "game" | "text"): void {
  writeJson("mode", mode);
}

/** The chapter read most recently, for "Continuar". */
export function lastPlayed(): { series: string; chapter: string } | null {
  return readJson("last", null);
}

export function storeLastPlayed(series: string, chapter: string): void {
  writeJson("last", { series, chapter });
}

/** Every ending and passage the reader has ever reached, per chapter. Only grows; undo and restart keep it. */
export function loadFound(series: string): Record<string, Found> {
  return readJson(`${series}:found`, {});
}

export function recordFound(series: string, chapter: string, what: { ending?: string; passage?: string }): void {
  const all = loadFound(series);
  const mine = all[chapter] ?? { endings: [], passages: [] };
  if (what.ending && !mine.endings.includes(what.ending)) mine.endings.push(what.ending);
  if (what.passage && !mine.passages.includes(what.passage)) mine.passages.push(what.passage);
  writeJson(`${series}:found`, { ...all, [chapter]: mine });
}
