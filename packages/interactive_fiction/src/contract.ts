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

/** Someone credited on the series' "about" page, with links to their profiles. */
export interface Credit {
  name: string;
  role: string;
  /** Link text → https URL, e.g. `{ "GitHub": "https://github.com/…" }`. */
  links: Record<string, string>;
}

/**
 * A published picture's lighter encodings, beside the original: each a list of `[path, width]`,
 * narrowest first. `width` and `height` are the original's, in pixels.
 */
export interface ImageSet {
  width: number;
  height: number;
  avif: [path: string, width: number][];
  webp: [path: string, width: number][];
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
  credits: Credit[];
  game: GameConfig;
  /** Every published JPEG and PNG of the series, by the path passages and scenes name it with. */
  images: Record<string, ImageSet>;
  chapters: ChapterSummary[];
}

/** `<series>/<chapter>.json`: the story, its scenes and what it holds to discover. */
export type ChapterData = Story & {
  /** Changes whenever the chapter's passages change; a save records the version it was made on. */
  version: string;
  scenes: SceneFile | null;
  discoveries: ChapterDiscoveries | null;
};

export const LIBRARY_FILE = "library.json";

export function chapterFile(series: string, chapter: string): string {
  return `${series}/${chapter}.json`;
}
