/** Reads a series folder under stories/: its manifest and every chapter, parsed. */

import { readFileSync, readdirSync, existsSync } from "node:fs";
import { join } from "node:path";
import type { Carry } from "../src/contract.ts";
import { parseStory, type Story } from "../src/engine/source.ts";

export interface ChapterEntry {
  id: string;
  source: string;
  draft?: boolean;
  /** Point-and-click scene file for this chapter, relative to the series folder. */
  scenes?: string;
}

export interface SeriesManifest {
  title: string;
  chapters: ChapterEntry[];
  carry?: Carry;
  /** Paragraphs for the "about" page: credits, how the art was made. */
  about?: string[];
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
