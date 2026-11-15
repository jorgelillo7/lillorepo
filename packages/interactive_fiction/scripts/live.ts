/**
 * What a deploy must have put online, compared with the build it uploaded: the
 * same chapters at the same versions, no draft, the response headers of
 * `public/_headers` (those of `/assets/*` on the hashed files too), every file
 * the page loads, and a share page per series.
 */

import type { ChapterData, SeriesEntry } from "../src/contract.ts";

/** One site as the check sees it: the build on disk, or the deployed one. */
export interface Snapshot {
  library: SeriesEntry[];
  /** `series/chapter` → the chapter's version; a chapter that did not load is missing. */
  versions: Record<string, string>;
}

export function versionsOf(library: SeriesEntry[], chapter: (series: string, id: string) => ChapterData | undefined): Record<string, string> {
  const versions: Record<string, string> = {};
  for (const s of library) {
    for (const c of s.chapters) {
      const data = chapter(s.id, c.id);
      if (data) versions[`${s.id}/${c.id}`] = data.version;
    }
  }
  return versions;
}

/** Every difference between the build and the live site that means the deploy did not land, or landed wrong. */
export function contentProblems(built: Snapshot, live: Snapshot): string[] {
  const problems: string[] = [];
  const ids = (lib: SeriesEntry[]) => lib.flatMap((s) => s.chapters.map((c) => `${s.id}/${c.id}`));
  for (const s of live.library) {
    for (const c of s.chapters) if (c.draft) problems.push(`${s.id}/${c.id} is live and marked draft`);
  }
  const want = ids(built.library);
  const have = new Set(ids(live.library));
  for (const id of want) if (!have.has(id)) problems.push(`${id} is in the build and not live`);
  for (const id of have) if (!want.includes(id)) problems.push(`${id} is live and not in the build`);
  for (const id of want) {
    if (!have.has(id)) continue;
    if (!live.versions[id]) problems.push(`${id} is listed live and its data does not load`);
    else if (live.versions[id] !== built.versions[id]) problems.push(`${id} is live at version ${live.versions[id]}, the build is ${built.versions[id]}`);
  }
  return problems;
}

/** The headers of one block (`/*` unless named) of a Cloudflare `_headers` file, by lower-cased name. */
export function expectedHeaders(headersFile: string, block = "/*"): Record<string, string> {
  const found: Record<string, string> = {};
  let inBlock = false;
  for (const line of headersFile.split("\n")) {
    if (line.startsWith("#") || !line.trim()) continue;
    if (!/^\s/.test(line)) {
      inBlock = line.trim() === block;
      continue;
    }
    if (!inBlock) continue;
    const at = line.indexOf(":");
    found[line.slice(0, at).trim().toLowerCase()] = line.slice(at + 1).trim();
  }
  return found;
}

/** Headers the page must be served with and is not; `sent` reads one by lower-cased name. */
export function headerProblems(expected: Record<string, string>, sent: (name: string) => string | null): string[] {
  return Object.entries(expected).flatMap(([name, value]) => {
    const got = sent(name);
    if (got === null) return [`response header ${name} is missing`];
    return got.trim() === value ? [] : [`response header ${name} is "${got}", expected "${value}"`];
  });
}

/** The scripts and stylesheets a built page loads from its own origin, as written in its HTML. */
export function pageAssets(html: string): string[] {
  return [...html.matchAll(/<(?:script|link)\b[^>]*\s(?:src|href)="([^"]+)"/g)].map((m) => m[1]).filter((u) => !/^(?:https?:|data:|#)/.test(u));
}

/** What is wrong with a series' share page as served: its og:title must name the series. */
export function sharePageProblems(path: string, status: number, html: string, title: string): string[] {
  if (status !== 200) return [`${path} answered ${status}`];
  const m = /<meta property="og:title" content="([^"]*)"/.exec(html);
  const esc = title.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  if (!m) return [`${path} has no og:title`];
  return m[1] === esc ? [] : [`${path} has og:title "${m[1]}", expected "${esc}"`];
}
