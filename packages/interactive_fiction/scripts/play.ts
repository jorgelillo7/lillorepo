/**
 * Plays every built chapter end to end in a real (headless) Chrome, the way a
 * reader would: for each chapter the explorer's shortest path to an ending is
 * clicked through — hotspot or link alike, by its choice label — typing any
 * code the chapter asks for. Fails on a choice that cannot be found, a chapter
 * that does not reach its end panel, or any console error.
 *
 *   npm run play          builds (drafts included, local only) and plays
 *
 * Needs Google Chrome; set CHROME_PATH if it is not in the usual place.
 */

import { spawn, type ChildProcess } from "node:child_process";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { chapterFile, LIBRARY_FILE, type ChapterData, type SeriesEntry } from "../src/contract.ts";
import { exploreSeries } from "../src/engine/explore.ts";
import { sleep, waitFor, withChrome, type Devtools } from "./chrome.ts";

const ROOT = new URL("../", import.meta.url).pathname;
const DIST = join(ROOT, "dist/stories");
const WEB_PORT = 4179;
const CDP_PORT = 9399;
const BASE = `http://localhost:${WEB_PORT}/`;

/** Clear the way to the next choice: read the whole passage and skip the door. */
async function settle(c: Devtools): Promise<void> {
  await c.ev(`document.querySelector('[data-pace=all]')?.click(); document.querySelector('.door-transition')?.remove(); true`);
  await sleep(120);
}

/** Wait for what `expression` finds to be on screen — a page with heavy images takes a moment — up to `ms`. */
async function appears(c: Devtools, expression: string, ms = 8000): Promise<boolean> {
  for (let waited = 0; waited < ms; waited += 200) {
    await settle(c);
    if (await c.ev<boolean>(`!!(${expression})`)) return true;
    await sleep(80);
  }
  return false;
}

async function playChapter(c: Devtools, series: SeriesEntry, chapter: string, path: string[]): Promise<string | null> {
  await c.ev(`localStorage.removeItem('if:v1:${series.id}:${chapter}'); true`);
  // A fresh document at the chapter's own URL. Changing only the hash and then
  // reloading raced: a reload that ran before the hash change committed
  // reloaded the previous chapter.
  await c.send("Page.navigate", { url: `${BASE}?play=${Date.now()}#/${series.id}/${chapter}` });
  for (const step of path) {
    await settle(c);
    const typed = /^«(.*)»$/.exec(step);
    if (typed) {
      await appears(c, `document.querySelector('input[data-bind]')`);
      const ok = await c.ev<boolean>(`(() => { const i = document.querySelector('input[data-bind]'); if (!i) return false;
        i.value = ${JSON.stringify(typed[1])}; i.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
      if (!ok) return `no code field for ${step}`;
      continue;
    }
    const target = `[...document.querySelectorAll('[data-choice]')].find(e => e.dataset.choice === ${JSON.stringify(step)} && e.offsetParent !== null)`;
    // A choice waiting in another view: step through to it first, as a reader would.
    const door = `[...document.querySelectorAll('.hotspot[data-view]')].find(e => JSON.parse(e.dataset.reaches).includes(${JSON.stringify(step)}))`;
    if (!(await c.ev<boolean>(`!!(${target})`)) && (await c.ev<boolean>(`!!(${door})`))) {
      await c.click(door);
      await sleep(300);
      await settle(c);
    }
    // A choice inside a closed hotspot menu: open the menu first, as a reader would.
    const menu = `(() => { const o = [...document.querySelectorAll('.hotspot-menu[hidden] [data-choice]')].find(e => e.dataset.choice === ${JSON.stringify(step)});
      return o && document.querySelector('.hotspot[data-menu="' + o.closest('.hotspot-menu').dataset.menuOf + '"]'); })()`;
    if (!(await c.ev<boolean>(`!!(${target})`)) && (await c.ev<boolean>(`!!(${menu})`))) await c.click(menu);
    if (!(await appears(c, target)) || !(await c.click(target))) {
      const visible = await c.ev<string>(`[...document.querySelectorAll('[data-choice]')].map(e => e.dataset.choice).join(' | ')`);
      const page = await c.ev<string>(`location.hash + ' — ' + document.body.innerText.replace(/\\s+/g, ' ').slice(0, 200)`);
      return `could not find «${step}» — choices on screen: ${visible || "none"} — page ${page}`;
    }
    await sleep(350);
  }
  await settle(c);
  return (await c.ev<boolean>(`!!document.querySelector('.end-panel')`)) ? null : "the chapter did not reach its end panel";
}

async function main(): Promise<number> {
  const library = JSON.parse(readFileSync(join(DIST, LIBRARY_FILE), "utf8")) as SeriesEntry[];
  const web: ChildProcess = spawn(join(ROOT, "node_modules/.bin/vite"), ["preview", "--port", String(WEB_PORT), "--strictPort"], {
    cwd: ROOT,
    stdio: "ignore",
  });
  let failures = 0;
  try {
    await waitFor(BASE, "vite preview");
    await withChrome(CDP_PORT, async (c) => {
      for (const series of library) {
        const data = series.chapters.map((ch) => JSON.parse(readFileSync(join(DIST, chapterFile(series.id, ch.id)), "utf8")) as ChapterData);
        const reports = exploreSeries(data, series.carry ?? undefined);
        for (const [i, ch] of series.chapters.entries()) {
          const d = data[i].discoveries;
          const report = reports[i];
          const ending = d?.endings[0];
          const path = !ending ? undefined : d!.kind === "codes" ? report.endPaths[ending] : report.deadEndPaths[ending];
          if (!path) {
            console.log(`· ${series.id}/${ch.id}: no ending to play to`);
            continue;
          }
          const before = c.errors.length;
          const problem = (await playChapter(c, series, ch.id, path)) ?? (c.errors.length > before ? `console: ${c.errors.slice(before).join(" / ")}` : null);
          console.log(`${problem ? "✗" : "✓"} ${series.id}/${ch.id} → ${ending} in ${path.length} clicks${problem ? ` — ${problem}` : ""}`);
          if (problem) failures++;
        }
      }
    });
  } finally {
    web.kill();
  }
  return failures ? 1 : 0;
}

process.exit(await main());
