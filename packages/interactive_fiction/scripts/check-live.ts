/**
 * Checks a deployed site against the build in dist/, read-only: `npm run deploy`
 * runs it right after the upload, and it can be run at any time.
 *
 *   npm run check:live [-- <url>]     default: the public reader
 *
 * Fails when a chapter is missing, extra, marked draft or at another version
 * than the build, when a response header of public/_headers is missing or
 * different, or when a file the page loads does not answer 200.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { chapterFile, LIBRARY_FILE, type ChapterData, type SeriesEntry } from "../src/contract.ts";
import { sleep } from "./chrome.ts";
import { contentProblems, expectedHeaders, headerProblems, pageAssets, versionsOf } from "./live.ts";

const ROOT = new URL("../", import.meta.url).pathname;
const DIST = join(ROOT, "dist");
const site = (process.argv[2] ?? process.env.SITE_URL ?? "https://interactive-fiction.jorgelillo.workers.dev").replace(/\/*$/, "/");
/** A new deploy takes a moment to answer everywhere. */
const ATTEMPTS = 4;

const readDist = <T>(path: string) => JSON.parse(readFileSync(join(DIST, path), "utf8")) as T;

async function get(path: string): Promise<Response> {
  return fetch(`${site}${path}${path.includes("?") ? "&" : "?"}check=${Date.now()}`, { redirect: "follow" });
}

async function problemsNow(): Promise<string[]> {
  const builtLibrary = readDist<SeriesEntry[]>(`stories/${LIBRARY_FILE}`);
  const built = { library: builtLibrary, versions: versionsOf(builtLibrary, (s, c) => readDist<ChapterData>(`stories/${chapterFile(s, c)}`)) };

  const page = await get("");
  if (!page.ok) return [`${site} answered ${page.status}`];
  const problems = headerProblems(expectedHeaders(readFileSync(join(DIST, "_headers"), "utf8")), (name) => page.headers.get(name));
  for (const asset of pageAssets(await page.text())) {
    const res = await get(asset.replace(/^\.?\//, ""));
    if (!res.ok) problems.push(`${asset}, which the page loads, answered ${res.status}`);
  }

  const lib = await get(`stories/${LIBRARY_FILE}`);
  if (!lib.ok) return [...problems, `stories/${LIBRARY_FILE} answered ${lib.status}`];
  const liveLibrary = (await lib.json()) as SeriesEntry[];
  const liveVersions: Record<string, string> = {};
  for (const s of liveLibrary) {
    for (const c of s.chapters) {
      const res = await get(`stories/${chapterFile(s.id, c.id)}`);
      if (res.ok) liveVersions[`${s.id}/${c.id}`] = ((await res.json()) as ChapterData).version;
    }
  }
  return [...problems, ...contentProblems(built, { library: liveLibrary, versions: liveVersions })];
}

let problems: string[] = [];
for (let attempt = 1; attempt <= ATTEMPTS; attempt++) {
  try {
    problems = await problemsNow();
  } catch (e) {
    problems = [`could not check ${site}: ${(e as Error).message}`];
  }
  if (!problems.length) break;
  if (attempt < ATTEMPTS) await sleep(5000);
}
for (const p of problems) console.log(`✗ ${p}`);
if (problems.length) {
  console.error(`\n${site} does not serve the build in dist/.`);
  process.exit(1);
}
console.log(`✓ ${site} serves the build in dist/: chapters, versions, headers and page files.`);
