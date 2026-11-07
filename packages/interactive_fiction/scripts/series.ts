/** Reads a series folder under stories/: its manifest and every chapter, parsed. */

import { readFileSync, readdirSync, existsSync, realpathSync, statSync } from "node:fs";
import { homedir } from "node:os";
import { isAbsolute, join, resolve } from "node:path";
import type { Carry, Credit } from "../src/contract.ts";
import { parseStory, parseTwee, type Story } from "../src/engine/source.ts";

export interface ChapterEntry {
  id: string;
  /**
   * The chapter, relative to `sourceRoot` when the series has one: one Twee or
   * Twine HTML file, or — as Tweego takes them — a list of folders and files
   * whose `.twee`/`.tw` passages, `.css` stylesheets and `.js` scripts make
   * one story.
   */
  source: string | string[];
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

export interface SourceFile {
  path: string;
  text: string;
}

/**
 * One Twee text from Tweego-style source files, in the order given: passages
 * as they are, each stylesheet as a `stylesheet` passage, each script as a
 * `script` passage (which the parser refuses unless empty). Other files are
 * not part of the story.
 */
export function joinSources(files: SourceFile[]): string {
  return files
    .map(({ path, text }) => {
      if (/\.(twee|tw)$/i.test(path)) return text;
      if (/\.css$/i.test(path)) return `:: ${path} [stylesheet]\n${text}`;
      if (/\.js$/i.test(path)) return `:: ${path} [script]\n${text}`;
      return "";
    })
    .filter(Boolean)
    .join("\n\n");
}

/** Every file under `path` (itself, if it is a file), sorted, as Tweego reads a folder. */
function filesUnder(root: string, path: string): SourceFile[] {
  const full = join(root, path);
  if (!existsSync(full)) throw new Error(`Chapter source ${full} not found.`);
  if (!statSync(full).isDirectory()) return [{ path, text: readFileSync(full, "utf8") }];
  return readdirSync(full)
    .filter((name) => !name.startsWith("."))
    .sort()
    .flatMap((name) => filesUnder(root, join(path, name)));
}

function readChapter(sourceDir: string, source: string | string[]): Story {
  if (typeof source === "string" && !statSync(join(sourceDir, source)).isDirectory()) {
    return parseStory(readFileSync(join(sourceDir, source), "utf8"));
  }
  const paths = typeof source === "string" ? [source] : source;
  return parseTwee(joinSources(paths.flatMap((p) => filesUnder(sourceDir, p))));
}

export function loadSeries(id: string): Series {
  // The real path: a series folder may be a link into the author's clone, and its `..` must mean his repository.
  const dir = realpathSync(join(STORIES_DIR, id));
  const manifest = JSON.parse(readFileSync(join(dir, "series.json"), "utf8")) as SeriesManifest;
  const sourceDir = sourceDirOf(dir, manifest.sourceRoot);
  if (!existsSync(sourceDir)) throw new Error(`${id}: sourceRoot ${sourceDir} not found — clone the author's repository there.`);
  const stories = manifest.chapters.map((c) => readChapter(sourceDir, c.source));
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
