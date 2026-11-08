/**
 * Play the draft's chapter to an ending as a player would, in headless Chrome
 * at a phone held in landscape: the shortest path to an ending, each choice
 * made by touching its thing in the room when the room holds it, else in the
 * text. Fails on a choice found nowhere, a missing ending or a console error.
 *
 *   node check.ts        (after npm run prepare-data)
 */

import { spawn } from "node:child_process";
import { mkdtempSync, readFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { createServer } from "vite";
import { Runtime } from "../../src/engine/runtime.ts";
import { devtools, sleep, waitFor } from "../../scripts/chrome.ts";

const PORT = 5311;
const CDP_PORT = 9452;
const here = dirname(new URL(import.meta.url).pathname);
const data = JSON.parse(readFileSync(join(here, "public/01.json"), "utf8"));

/** The labels of the shortest path's choices, from the start to a passage with nothing left to click. */
function shortestPath(): string[] {
  const rt = new Runtime(data);
  const queue = [{ passage: data.start as string, vars: rt.start(), path: [] as string[] }];
  const seen = new Set<string>();
  while (queue.length) {
    const { passage, vars, path } = queue.shift()!;
    const v = structuredClone(vars);
    const page = rt.visit(v, passage);
    if (!page.actions.length) return path;
    const key = page.passage + JSON.stringify(v);
    if (seen.has(key)) continue;
    seen.add(key);
    for (const a of page.actions) if (a.kind === "link") queue.push({ passage: a.target, vars: v, path: [...path, a.label] });
  }
  throw new Error("No ending reachable through links.");
}

const steps = shortestPath();
const server = await createServer({ root: here, logLevel: "silent", server: { port: PORT, strictPort: true } });
await server.listen();
const chrome = spawn("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ["--headless=new", `--remote-debugging-port=${CDP_PORT}`, `--user-data-dir=${mkdtempSync(join(tmpdir(), "check-"))}`, "about:blank"], { stdio: "ignore" });
let failed = false;
try {
  await waitFor(`http://127.0.0.1:${CDP_PORT}/json/version`, "Chrome");
  const c = await devtools(CDP_PORT);
  await c.send("Page.enable");
  await c.send("Emulation.setDeviceMetricsOverride", { width: 844, height: 390, deviceScaleFactor: 1, mobile: true });
  await c.send("Page.navigate", { url: `http://localhost:${PORT}/` });
  for (let i = 0; i < 240 && !(await c.ev("!document.getElementById('title-start').disabled")); i++) await sleep(250);
  await c.ev("document.getElementById('title-start').click()");
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
    const scene = await c.ev<string>("document.getElementById('world').hidden ? (document.getElementById('flat').hidden ? 'text only' : '2D') : '3D'");
    console.log(`${where ? "✓" : "✗"} ${step} — ${where || "found nowhere"} → ${scene}`);
    if (!where) failed = true;
  }
  await readAll();
  const end = await c.ev<string>("document.getElementById('subs-text').innerText.trim().split('\\n').pop()");
  console.log(`  ends on: ${end}`);
  if (c.errors.length) {
    console.log(`✗ console errors:\n${c.errors.join("\n")}`);
    failed = true;
  }
  c.close();
} finally {
  chrome.kill();
  await server.close();
}
process.exit(failed ? 1 : 0);
