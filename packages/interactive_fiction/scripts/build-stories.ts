/**
 * Validates every series under stories/ and writes what the reader loads to
 * public/stories/. Exits non-zero on any validation error, so a chapter the
 * reader cannot run never reaches a build.
 *
 * Chapters marked `draft` are left out unless STORIES_DRAFTS=1: a draft the
 * author has not published must not reach a public upload by accident.
 */

import { cpSync, existsSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { validate } from "../src/engine/validate.ts";
import type { Story } from "../src/engine/source.ts";
import { loadSeries, seriesIds } from "./series.ts";

const OUT = new URL("../public/stories/", import.meta.url).pathname;
const WITH_DRAFTS = process.env.STORIES_DRAFTS === "1";

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

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
const library: unknown[] = [];
let failed = false;

for (const id of seriesIds()) {
  const series = loadSeries(id);
  const outDir = join(OUT, id);
  mkdirSync(outDir, { recursive: true });
  const chapters = series.manifest.chapters.flatMap((entry, i) => {
    const story = series.stories[i];
    if (entry.draft && !WITH_DRAFTS) {
      console.log(`· ${id}/${entry.id} is a draft — left out (STORIES_DRAFTS=1 to include it)`);
      return [];
    }
    const issues = validate(story);
    for (const issue of issues) {
      const where = issue.passage ? ` [${issue.passage}]` : "";
      console.log(`${issue.level === "error" ? "✗" : "·"} ${id}/${entry.id}${where} ${issue.message}`);
    }
    if (issues.some((x) => x.level === "error")) failed = true;
    writeFileSync(join(outDir, `${entry.id}.json`), JSON.stringify(rebaseStory(story, `stories/${id}/`)));
    return [{ id: entry.id, title: story.title, draft: Boolean(entry.draft) }];
  });
  if (existsSync(join(series.dir, "resources"))) {
    cpSync(join(series.dir, "resources"), join(outDir, "resources"), { recursive: true });
  }
  library.push({ id, title: series.manifest.title, carry: series.manifest.carry ?? null, chapters });
  console.log(`✓ ${id}: ${chapters.length} chapters`);
}

writeFileSync(join(OUT, "library.json"), JSON.stringify(library, null, 2));
if (failed) {
  console.error("Validation failed: fix the errors above.");
  process.exit(1);
}
