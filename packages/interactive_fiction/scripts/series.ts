/** Reads a series folder under stories/: its manifest and every chapter, parsed. */

import { readFileSync, readdirSync, existsSync, realpathSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
import type { Carry, Credit } from "../src/contract.ts";
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
  /** Paragraphs for the "about" page: how the story and the art were made. */
  about?: string[];
  /** Who made it, shown on the "about" page and the title screen. */
  credits?: Credit[];
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
  // Through the real path: a series folder may be a link into the author's clone, and `..` must mean his repository.
  const sourceDir = sourceDirOf(realpathSync(dir), manifest.sourceRoot);
  if (!existsSync(sourceDir)) throw new Error(`${id}: sourceRoot ${sourceDir} not found — clone the author's repository there.`);
  const stories = manifest.chapters.map((c) => parseStory(readFileSync(join(sourceDir, c.source), "utf8")));
  return { id, dir, sourceDir, manifest, stories };
}

/** Problems in a series' credits: every entry needs a name and a role, and every link an https URL. */
export function validateCredits(credits: Credit[]): string[] {
  const errors: string[] = [];
  for (const [i, c] of credits.entries()) {
    const who = c.name?.trim() || `#${i + 1}`;
    if (!c.name?.trim()) errors.push(`credit ${who}: no name.`);
    if (!c.role?.trim()) errors.push(`credit ${who}: no role.`);
    for (const [label, url] of Object.entries(c.links ?? {})) {
      let ok = false;
      try {
        ok = new URL(url).protocol === "https:";
      } catch {
        // Not a URL at all.
      }
      if (!ok) errors.push(`credit ${who}: link "${label}" is not an https URL.`);
    }
  }
  return errors;
}
