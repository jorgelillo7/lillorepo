/**
 * Play one of the draft's chapters to an ending as a player would, in headless
 * Chrome at a phone held in landscape: the shortest path to an ending, each
 * choice made by touching its thing in the room when the room holds it, else
 * in the text. Fails on a title or "Acerca de" that does not fit a phone in
 * landscape, a choice found nowhere, a 3D hotspot with no place in the room, a
 * fade between rooms that never lifts, an ending without the next chapter's
 * way on, or a console error.
 *
 *   node check.ts [chapter] [--via <passage>]   (after npm run prepare-data; default 01)
 *
 * `--via` takes the shortest path that passes through a passage, to play a
 * room the shortest path skips.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { createServer } from "vite";
import { outcomeOf } from "../../src/app/progression.ts";
import type { SeriesEntry } from "../../src/contract.ts";
import { Runtime } from "../../src/engine/runtime.ts";
import { sleep, withChrome } from "../../scripts/chrome.ts";

const PORT = 5311;
const CDP_PORT = 9452;
const here = dirname(new URL(import.meta.url).pathname);
const args = process.argv.slice(2);
const via = args.includes("--via") ? args[args.indexOf("--via") + 1] : undefined;
const chapter = args.find((a, i) => !a.startsWith("--") && args[i - 1] !== "--via") ?? "01";
const data = JSON.parse(readFileSync(join(here, `public/${chapter}.json`), "utf8"));
const series = (JSON.parse(readFileSync(join(here, "public/library.json"), "utf8")) as SeriesEntry[])[0];
const nextChapter = series.chapters[series.chapters.findIndex((c) => c.id === chapter) + 1];

/**
 * The labels of the shortest path's choices, from the start to a passage that
 * ends the chapter (an unwritten dead end does not), through `via` if given.
 */
function shortestPath(): string[] {
  const rt = new Runtime(data);
  const queue = [{ passage: data.start as string, vars: rt.start(), path: [] as string[], passed: !via }];
  const seen = new Set<string>();
  while (queue.length) {
    const { passage, vars, path, passed: before } = queue.shift()!;
    const v = structuredClone(vars);
    const page = rt.visit(v, passage);
    const passed = before || page.passage === via;
    if (passed && outcomeOf(page, v, series.carry).ended) return path;
    const key = page.passage + passed + JSON.stringify(v);
    if (seen.has(key)) continue;
    seen.add(key);
    for (const a of page.actions) {
      if (a.kind === "link") {
        queue.push({ passage: a.target, vars: v, path: [...path, a.label], passed });
        continue;
      }
      // A choice that reveals text: it either moves on by itself, or offers the links it revealed.
      const after = structuredClone(v);
      const r = rt.reveal(after, a);
      if (r.goto) queue.push({ passage: r.goto, vars: after, path: [...path, a.label], passed });
      else for (const b of r.actions) if (b.kind === "link") queue.push({ passage: b.target, vars: after, path: [...path, a.label, b.label], passed });
    }
  }
  throw new Error(`No ending reachable${via ? ` via "${via}"` : ""}.`);
}

const steps = shortestPath();
const server = await createServer({ root: here, logLevel: "silent", server: { port: PORT, strictPort: true } });
await server.listen();
let failed = false;
try {
  await withChrome(CDP_PORT, async (c) => {
    await c.send("Page.enable");
    // The smallest landscape phone, with Safari's bars: the title and "Acerca de" must fit without scrolling.
    await c.send("Emulation.setDeviceMetricsOverride", { width: 750, height: 330, deviceScaleFactor: 1, mobile: true });
    await c.send("Page.navigate", { url: `http://localhost:${PORT}/` });
    const start = `document.querySelector('[data-chapter="${chapter}"]')`;
    for (let i = 0; i < 240 && !(await c.ev(`!!${start}`)); i++) await sleep(250);
    const overflow = (id: string) => `(() => { const e = document.getElementById('${id}'); return e.scrollHeight > e.clientHeight; })()`;
    if (await c.ev(overflow("title"))) {
      console.log("✗ the title screen does not fit 750×330");
      failed = true;
    }
    await c.ev("document.getElementById('title-credits').click()");
    if (await c.ev(overflow("about"))) {
      console.log("✗ «Acerca de» does not fit 750×330");
      failed = true;
    }
    await c.ev("document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))");
    if (!(await c.ev("document.getElementById('about').hidden"))) {
      console.log("✗ Escape does not close «Acerca de»");
      failed = true;
    }
    await c.send("Emulation.setDeviceMetricsOverride", { width: 844, height: 390, deviceScaleFactor: 1, mobile: true });
    await c.ev(`${start}.click()`);
    await sleep(1500);
    const readAll = async () => {
      for (let k = 0; k < 40 && (await c.ev("!document.getElementById('subs').hidden && !document.getElementById('subs-next').hidden")); k++) {
        await c.ev("document.getElementById('subs-next').click()");
        await sleep(60);
      }
    };
    for (const step of steps) {
      await readAll();
      const choice = JSON.stringify(step);
      const where = await c.ev<string>(`(() => {
        const prompt = document.getElementById('prompt-cancel');
        for (const spot of document.querySelectorAll('.spot')) {
          spot.click();
          const b = [...document.querySelectorAll('#prompt-actions button')].find((b) => b.textContent === ${choice});
          if (b) { const where = 'room: ' + spot.getAttribute('aria-label'); b.click(); return where; }
          prompt.click();
        }
        const link = [...document.querySelectorAll('#subs-text tw-link')].find((l) => l.dataset.choice === ${choice});
        if (link) { link.click(); return 'text'; }
        return '';
      })()`);
      await sleep(1200);
      // A fade between rooms that never lifted would leave a black screen a real tap cannot get through.
      for (let i = 0; i < 40 && (await c.ev("document.getElementById('veil').classList.contains('on')")); i++) await sleep(250);
      if (await c.ev("document.getElementById('veil').classList.contains('on')")) {
        console.log(`✗ ${step} — the fade to the next room never lifted`);
        failed = true;
      }
      const scene = await c.ev<string>("document.getElementById('world').hidden ? (document.getElementById('flat').hidden ? 'text only' : '2D') : '3D'");
      // A 3D hotspot without an anchor would sit unplaced in a corner, yet still take a click.
      const unplaced = await c.ev<string[]>("[...document.querySelectorAll('.spot:not(.rect)')].filter((s) => !s.style.left).map((s) => s.getAttribute('aria-label'))");
      if (unplaced.length) {
        console.log(`✗ no place in the room for: ${unplaced.join(", ")}`);
        failed = true;
      }
      console.log(`${where ? "✓" : "✗"} ${step} — ${where || "found nowhere"} → ${scene}`);
      if (!where) failed = true;
    }
    await readAll();
    const end = await c.ev<string>("document.getElementById('subs-text').innerText.trim().split('\\n').pop()");
    console.log(`  ends on: ${end}`);
    const way = await c.ev<string>("document.getElementById('subs-end').hidden ? '' : document.getElementById('subs-end').innerText.replace(/\\s+/g, ' ').trim()");
    console.log(`  end bar: ${way || "missing"}`);
    if (!way || (nextChapter && !(await c.ev("!document.getElementById('subs-next-chapter').hidden")))) {
      console.log("✗ the ending offers no way on");
      failed = true;
    } else if (nextChapter) {
      await c.ev("document.getElementById('subs-next-chapter').click()");
      await sleep(2500);
      const opened = await c.ev<string>("document.getElementById('subs').hidden ? '' : document.getElementById('subs-text').innerText.trim().split('\\n')[0]");
      console.log(`${opened ? "✓" : "✗"} ${nextChapter.id} opens: ${opened || "nothing"}`);
      if (!opened) failed = true;
    }
    if (c.errors.length) {
      console.log(`✗ console errors:\n${c.errors.join("\n")}`);
      failed = true;
    }
  }, { gpu: true });
} finally {
  await server.close();
}
process.exit(failed ? 1 : 0);
