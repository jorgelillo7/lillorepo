/** Reads a series folder under stories/: its manifest and every chapter, parsed. */

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import { parseStory, type Story } from "../src/engine/source.ts";

export interface ChapterEntry {
  id: string;
  source: string;
  draft?: boolean;
}

export interface SeriesManifest {
  title: string;
  chapters: ChapterEntry[];
  /** The end code of one chapter is pre-filled into this input of the next. */
  carry?: { from: string; to: string };
}

export interface Series {
  id: string;
  dir: string;
  manifest: SeriesManifest;
  stories: Story[];
}

export const STORIES_DIR = new URL("../stories/", import.meta.url).pathname;

export function seriesIds(): string[] {
  if (!existsSync(STORIES_DIR)) return [];
  return readdirSync(STORIES_DIR).filter((d) => existsSync(join(STORIES_DIR, d, "series.json")));
}

export function loadSeries(id: string): Series {
  const dir = join(STORIES_DIR, id);
  const manifest = JSON.parse(readFileSync(join(dir, "series.json"), "utf8")) as SeriesManifest;
  const stories = manifest.chapters.map((c) => parseStory(readFileSync(join(dir, c.source), "utf8")));
  return { id, dir, manifest, stories };
}
