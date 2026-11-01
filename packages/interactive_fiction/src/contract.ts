/**
 * The one definition of what the build writes to `public/stories/` and the
 * app reads from it. Both sides import these types, so they cannot drift.
 */

import type { ChapterDiscoveries } from "./engine/discoveries.ts";
import type { GameConfig } from "./engine/game.ts";
import type { SceneFile } from "./engine/scenes.ts";
import type { Story } from "./engine/source.ts";

/** The end code of one chapter, pre-filled into this input of the next. */
export interface Carry {
  from: string;
  to: string;
}

export interface ChapterSummary {
  id: string;
  title: string;
  draft: boolean;
}

/** One entry of `library.json`. */
export interface SeriesEntry {
  id: string;
  title: string;
  carry: Carry | null;
  about: string[];
  game: GameConfig;
  chapters: ChapterSummary[];
}

/** `<series>/<chapter>.json`: the story, its scenes and what it holds to discover. */
export type ChapterData = Story & {
  scenes: SceneFile | null;
  discoveries: ChapterDiscoveries | null;
};

export const LIBRARY_FILE = "library.json";

export function chapterFile(series: string, chapter: string): string {
  return `${series}/${chapter}.json`;
}
