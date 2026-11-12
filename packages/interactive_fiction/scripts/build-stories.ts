/**
 * Validates every series under stories/ and writes what the reader loads to
 * public/stories/ (the shapes in src/contract.ts). Exits non-zero on any
 * validation error, so a chapter the reader cannot run never reaches a build.
 *
 * Chapters marked `draft` are left out unless STORIES_DRAFTS=1: a draft the
 * author has not published must not reach a public upload by accident.
 *
 * With STORIES_PUBLISH=1 (what `npm run deploy` sets) it also refuses sources that are not their
 * repository's default branch as its origin holds it (scripts/source-guard.ts), unless
 * STORIES_ALLOW_UNPUBLISHED=1 asks for a deliberate preview.
 */

import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { createHash } from "node:crypto";
import { join } from "node:path";
import { chapterFile, LIBRARY_FILE, type ChapterData, type ChapterSummary, type SeriesEntry } from "../src/contract.ts";
import { discoveriesOf } from "../src/engine/discoveries.ts";
import { exploreSeries } from "../src/engine/explore.ts";
import { validateGame, type GameConfig } from "../src/engine/game.ts";
import { validateScenes, type SceneFile } from "../src/engine/scenes.ts";
import type { Story } from "../src/engine/source.ts";
import { validate, variablesSet } from "../src/engine/validate.ts";
import { validateBible, type ArtBible } from "./art-bible.ts";
import { loadSeries, seriesIds, validateCredits, type Series } from "./series.ts";
import { publishProblems } from "./source-guard.ts";

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

/** A short digest of the passages: equal versions mean a save made on one fits the other. */
function storyVersion(story: Story): string {
  const hash = createHash("sha256");
  for (const p of story.passages) hash.update(`${p.name}\u0000${p.text}\u0000`);
  return hash.digest("hex").slice(0, 12);
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
  const copies: [string, string][] = [
    ...["resources", "scenes"].map((f): [string, string] => [join(series.dir, f), f]),
    ...series.manifest.chapters.flatMap((c): [string, string][] => (c.resources ? [[join(series.sourceDir, c.resources), "resources"]] : [])),
  ];
  for (const [from, to] of copies) {
    if (!existsSync(from)) continue;
    cpSync(from, join(outDir, to), { recursive: true, filter: (src) => !/\.[^/]+$/.test(src) || MEDIA.test(src) });
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
    const story = rebaseStory(series.stories[i], served);
    const data: ChapterData = {
      ...story,
      version: storyVersion(story),
      scenes: sceneFile,
      discoveries: discoveriesOf(reports[i]),
    };
    writeFileSync(join(OUT, chapterFile(id, entry.id)), JSON.stringify(data));
    published.push({ id: entry.id, title: series.stories[i].title, draft: Boolean(entry.draft) });
  });

  checkBible(series, scenes, chapters);
  report(`${id} [credits]`, validateCredits(series.manifest.credits ?? []));
  const game = loadGame(series, chapters);
  if (game.title?.image) game.title.image = served + game.title.image;
  copyMedia(series, outDir);
  console.log(`✓ ${id}: ${published.length} chapters`);
  return {
    id,
    title: series.manifest.title,
    carry: series.manifest.carry ?? null,
    about: series.manifest.about ?? [],
    credits: series.manifest.credits ?? [],
    game,
    chapters: published,
  };
}

if (process.env.STORIES_PUBLISH === "1") {
  const problems = publishProblems(seriesIds().map(loadSeries));
  if (problems.length && process.env.STORIES_ALLOW_UNPUBLISHED === "1") {
    for (const p of problems) console.log(`⚠ publishing anyway (STORIES_ALLOW_UNPUBLISHED=1): ${p}`);
  } else if (problems.length) {
    for (const p of problems) console.log(`✗ ${p}`);
    console.error(
      "Refusing to publish: a public deploy takes each story from its repository's default branch, clean and equal to its origin.\n" +
        "Pull or check out that branch, or set STORIES_ALLOW_UNPUBLISHED=1 for a deliberate preview.",
    );
    process.exit(1);
  }
}

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
const library = seriesIds().map(buildSeries);
writeFileSync(join(OUT, LIBRARY_FILE), JSON.stringify(library, null, 2));
if (failed) {
  console.error("Validation failed: fix the errors above.");
  process.exit(1);
}
