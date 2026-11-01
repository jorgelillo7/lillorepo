/** Reads a series folder under stories/: its manifest and every chapter, parsed. */

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
import type { Carry } from "../src/contract.ts";
import { parseStory, type Story } from "../src/engine/source.ts";

export interface ChapterEntry {
  id: string;
  /** The chapter's Twee or Twine HTML, relative to `sourceRoot` when the series has one. */
  source: string;
  /** A folder of media its passages reference (`resources/...`), relative like `source`; served as the series' `resources/`. */
  resources?: string;
  draft?: boolean;
  /** Point-and-click scene file for this chapter, relative to the series folder. */
  scenes?: string;
}

export interface SeriesManifest {
  title: string;
  /**
   * The author's own folder, typically his git clone, read in place so a
   * `git pull` is the whole import. Relative to the series folder, absolute,
   * or starting with `~/`. Without it, sources sit in the series folder.
   */
  sourceRoot?: string;
  chapters: ChapterEntry[];
  carry?: Carry;
  /** Paragraphs for the "about" page: credits, how the art was made. */
  about?: string[];
}

export interface Series {
  id: string;
  dir: string;
  /** Where chapter `source` and `resources` paths resolve. */
  sourceDir: string;
  manifest: SeriesManifest;
  stories: Story[];
}

export const STORIES_DIR = new URL("../stories/", import.meta.url).pathname;

export function seriesIds(): string[] {
  if (!existsSync(STORIES_DIR)) return [];
  return readdirSync(STORIES_DIR).filter((d) => existsSync(join(STORIES_DIR, d, "series.json")));
}

/** The folder chapter sources resolve against: the series folder, or its `sourceRoot`. */
export function sourceDirOf(seriesDir: string, sourceRoot: string | undefined, home = homedir()): string {
  if (!sourceRoot) return seriesDir;
  if (sourceRoot === "~" || sourceRoot.startsWith("~/")) return join(home, sourceRoot.slice(1));
  return isAbsolute(sourceRoot) ? sourceRoot : resolve(seriesDir, sourceRoot);
}

export function loadSeries(id: string): Series {
  const dir = join(STORIES_DIR, id);
  const manifest = JSON.parse(readFileSync(join(dir, "series.json"), "utf8")) as SeriesManifest;
  const sourceDir = sourceDirOf(dir, manifest.sourceRoot);
  if (!existsSync(sourceDir)) throw new Error(`${id}: sourceRoot ${sourceDir} not found — clone the author's repository there.`);
  const stories = manifest.chapters.map((c) => parseStory(readFileSync(join(sourceDir, c.source), "utf8")));
  return { id, dir, sourceDir, manifest, stories };
}
