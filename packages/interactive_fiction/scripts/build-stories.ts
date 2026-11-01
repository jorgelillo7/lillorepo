/**
 * Validates every series under stories/ and writes what the reader loads to
 * public/stories/ (the shapes in src/contract.ts). Exits non-zero on any
 * validation error, so a chapter the reader cannot run never reaches a build.
 *
 * Chapters marked `draft` are left out unless STORIES_DRAFTS=1: a draft the
 * author has not published must not reach a public upload by accident.
 */

import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { chapterFile, LIBRARY_FILE, type ChapterData, type ChapterSummary, type SeriesEntry } from "../src/contract.ts";
import { discoveriesOf } from "../src/engine/discoveries.ts";
import { exploreSeries } from "../src/engine/explore.ts";
import { validateGame, type GameConfig } from "../src/engine/game.ts";
import { validateScenes, type SceneFile } from "../src/engine/scenes.ts";
import type { Story } from "../src/engine/source.ts";
import { validate, variablesSet } from "../src/engine/validate.ts";
import { validateBible, type ArtBible } from "./art-bible.ts";
import { loadSeries, seriesIds, type Series } from "./series.ts";

const OUT = new URL("../public/stories/", import.meta.url).pathname;
const WITH_DRAFTS = process.env.STORIES_DRAFTS === "1";
/** Only media is published from a series folder; prompts, scripts and notes beside the art stay local. */
const MEDIA = /\.(png|jpe?g|webp|avif|gif|svg|mp3|ogg|webm|m4a)$/i;

let failed = false;

function report(where: string, messages: string[]): void {
  for (const m of messages) console.log(`✗ ${where} ${m}`);
  if (messages.length) failed = true;
}

function readJson<T>(path: string): T {
  return JSON.parse(readFileSync(path, "utf8")) as T;
}

/** Relative asset paths in passages and CSS point into the series folder once served. */
function rebase(text: string, prefix: string): string {
  return text
    .replace(/(src|href)="(?!https?:|data:|\/|#)([^"]+)"/g, `$1="${prefix}$2"`)
    .replace(/url\((['"]?)(?!https?:|data:|\/)([^)'"]+)\1\)/g, `url($1${prefix}$2$1)`);
}

function rebaseStory(story: Story, prefix: string): Story {
  return {
    ...story,
    stylesheet: rebase(story.stylesheet, prefix),
    passages: story.passages.map((p) => ({ ...p, text: rebase(p.text, prefix) })),
  };
}

/** Every chapter's scene file, parsed once; null for chapters without one. */
function loadScenes(series: Series): (SceneFile | null)[] {
  return series.manifest.chapters.map((c) => (c.scenes ? readJson<SceneFile>(join(series.dir, c.scenes)) : null));
}

function checkChapter(series: Series, i: number, scenes: SceneFile | null): void {
  const entry = series.manifest.chapters[i];
  const story = series.stories[i];
  const where = `${series.id}/${entry.id}`;
  const issues = validate(story);
  for (const issue of issues.filter((x) => x.level === "warning")) {
    console.log(`· ${where}${issue.passage ? ` [${issue.passage}]` : ""} ${issue.message}`);
  }
  report(
    where,
    issues.filter((x) => x.level === "error").map((x) => `${x.passage ? `[${x.passage}] ` : ""}${x.message}`),
  );
  if (scenes) {
    report(`${where} [scenes]`, validateScenes(story, scenes, (path) => existsSync(join(series.dir, path))));
  }
}

function checkBible(series: Series, scenes: (SceneFile | null)[], chapters: Record<string, Story>): void {
  const path = join(series.dir, "art-bible.json");
  if (!existsSync(path)) return;
  const images = scenes.flatMap((f) => (f ? Object.values(f.scenes).map((s) => s.image) : []));
  const exists = (p: string) => existsSync(join(series.dir, p));
  report(`${series.id} [art bible]`, validateBible(readJson<ArtBible>(path), chapters, images, exists));
}

function loadGame(series: Series, chapters: Record<string, Story>): GameConfig {
  const path = join(series.dir, "game.json");
  if (!existsSync(path)) return {};
  const game = readJson<GameConfig>(path);
  const setAnywhere = new Set(series.stories.flatMap((st) => [...variablesSet(st)]));
  report(`${series.id} [game]`, validateGame(game, chapters, setAnywhere, (p) => existsSync(join(series.dir, p))));
  return game;
}

function copyMedia(series: Series, outDir: string): void {
  for (const folder of ["resources", "scenes"]) {
    if (!existsSync(join(series.dir, folder))) continue;
    cpSync(join(series.dir, folder), join(outDir, folder), {
      recursive: true,
      filter: (src) => !/\.[^/]+$/.test(src) || MEDIA.test(src),
    });
  }
}

function buildSeries(id: string): SeriesEntry {
  const series = loadSeries(id);
  const served = `stories/${id}/`;
  const outDir = join(OUT, id);
  mkdirSync(outDir, { recursive: true });
  const chapters = Object.fromEntries(series.manifest.chapters.map((c, i) => [c.id, series.stories[i]]));
  const scenes = loadScenes(series);
  // Every chapter is explored, drafts too: a chapter that asks for the previous
  // one's code must be tried with every code that one can produce.
  const reports = exploreSeries(series.stories, series.manifest.carry);

  const published: ChapterSummary[] = [];
  series.manifest.chapters.forEach((entry, i) => {
    if (entry.draft && !WITH_DRAFTS) {
      console.log(`· ${id}/${entry.id} is a draft — left out (STORIES_DRAFTS=1 to include it)`);
      return;
    }
    checkChapter(series, i, scenes[i]);
    const own = scenes[i];
    const sceneFile: SceneFile | null = own && {
      ...own,
      scenes: Object.fromEntries(Object.entries(own.scenes).map(([k, s]) => [k, { ...s, image: served + s.image }])),
    };
    const data: ChapterData = {
      ...rebaseStory(series.stories[i], served),
      scenes: sceneFile,
      discoveries: discoveriesOf(reports[i]),
    };
    writeFileSync(join(OUT, chapterFile(id, entry.id)), JSON.stringify(data));
    published.push({ id: entry.id, title: series.stories[i].title, draft: Boolean(entry.draft) });
  });

  checkBible(series, scenes, chapters);
  const game = loadGame(series, chapters);
  if (game.title?.image) game.title.image = served + game.title.image;
  copyMedia(series, outDir);
  console.log(`✓ ${id}: ${published.length} chapters`);
  return {
    id,
    title: series.manifest.title,
    carry: series.manifest.carry ?? null,
    about: series.manifest.about ?? [],
    game,
    chapters: published,
  };
}

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
const library = seriesIds().map(buildSeries);
writeFileSync(join(OUT, LIBRARY_FILE), JSON.stringify(library, null, 2));
if (failed) {
  console.error("Validation failed: fix the errors above.");
  process.exit(1);
}
