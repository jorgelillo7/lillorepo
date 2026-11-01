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
import { existsSync, mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { chapterFile, LIBRARY_FILE, type ChapterData, type SeriesEntry } from "../src/contract.ts";
import { exploreSeries } from "../src/engine/explore.ts";

const ROOT = new URL("../", import.meta.url).pathname;
const DIST = join(ROOT, "dist/stories");
const WEB_PORT = 4179;
const CDP_PORT = 9399;
const BASE = `http://localhost:${WEB_PORT}/`;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function chromePath(): string {
  const candidates = [
    process.env.CHROME_PATH,
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium",
  ];
  const found = candidates.find((c) => c && existsSync(c));
  if (!found) throw new Error("Google Chrome not found: set CHROME_PATH.");
  return found;
}

async function waitFor(url: string, what: string): Promise<void> {
  for (let i = 0; i < 80; i++) {
    try {
      if ((await fetch(url)).ok) return;
    } catch {
      // Not up yet.
    }
    await sleep(250);
  }
  throw new Error(`${what} did not start.`);
}

/** A minimal Chrome DevTools Protocol client over the built-in WebSocket. */
async function devtools() {
  const pages = (await (await fetch(`http://127.0.0.1:${CDP_PORT}/json/list`)).json()) as {
    type: string;
    webSocketDebuggerUrl: string;
  }[];
  const ws = new WebSocket(pages.find((p) => p.type === "page")!.webSocketDebuggerUrl);
  await new Promise((r) => ws.addEventListener("open", r));
  let id = 0;
  const pending = new Map<number, (v: { result?: { result?: { value?: unknown } } }) => void>();
  const errors: string[] = [];
  ws.addEventListener("message", (m) => {
    const d = JSON.parse(String(m.data));
    if (d.method === "Runtime.exceptionThrown") errors.push(d.params.exceptionDetails.exception?.description ?? d.params.exceptionDetails.text);
    if (d.method === "Runtime.consoleAPICalled" && d.params.type === "error") errors.push(JSON.stringify(d.params.args));
    pending.get(d.id)?.(d);
    pending.delete(d.id);
  });
  const send = (method: string, params: object = {}) =>
    new Promise<{ result?: { result?: { value?: unknown } } }>((r) => {
      const i = ++id;
      pending.set(i, r);
      ws.send(JSON.stringify({ id: i, method, params }));
    });
  await send("Runtime.enable");
  const ev = async <T>(expression: string): Promise<T> =>
    (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result?.result?.value as T;
  /** A real mouse click (a user gesture), at the centre of the element the expression returns. */
  const click = async (expression: string): Promise<boolean> => {
    const box = await ev<{ x: number; y: number } | null>(`(() => { const e = ${expression}; if (!e) return null;
      e.scrollIntoView({ block: "center" }); const r = e.getBoundingClientRect(); return { x: r.x + r.width / 2, y: r.y + r.height / 2 }; })()`);
    if (!box) return false;
    for (const type of ["mousePressed", "mouseReleased"]) {
      await send("Input.dispatchMouseEvent", { type, x: box.x, y: box.y, button: "left", clickCount: 1 });
    }
    return true;
  };
  return { send, ev, click, errors, close: () => ws.close() };
}

type Devtools = Awaited<ReturnType<typeof devtools>>;

/** Clear the way to the next choice: read the whole passage and skip the door. */
async function settle(c: Devtools): Promise<void> {
  await c.ev(`document.querySelector('[data-pace=all]')?.click(); document.querySelector('.door-transition')?.remove(); true`);
  await sleep(120);
}

async function playChapter(c: Devtools, series: SeriesEntry, chapter: string, path: string[]): Promise<string | null> {
  await c.ev(`localStorage.removeItem('if:v1:${series.id}:${chapter}'); true`);
  await c.send("Page.navigate", { url: `${BASE}#/${series.id}/${chapter}` });
  await c.send("Page.reload");
  await sleep(1200);
  for (const step of path) {
    await settle(c);
    const typed = /^«(.*)»$/.exec(step);
    if (typed) {
      const ok = await c.ev<boolean>(`(() => { const i = document.querySelector('input[data-bind]'); if (!i) return false;
        i.value = ${JSON.stringify(typed[1])}; i.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
      if (!ok) return `no code field for ${step}`;
      continue;
    }
    const target = `[...document.querySelectorAll('[data-choice]')].find(e => e.dataset.choice === ${JSON.stringify(step)} && e.offsetParent !== null)`;
    if (!(await c.click(target))) {
      const visible = await c.ev<string>(`[...document.querySelectorAll('[data-choice]')].map(e => e.dataset.choice).join(' | ')`);
      return `could not find «${step}» — on screen: ${visible}`;
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
  const profile = mkdtempSync(join(tmpdir(), "if-play-"));
  const chrome = spawn(
    chromePath(),
    ["--headless=new", "--disable-gpu", "--window-size=1400,900", `--remote-debugging-port=${CDP_PORT}`, "--remote-debugging-address=127.0.0.1", `--user-data-dir=${profile}`, "about:blank"],
    { stdio: "ignore" },
  );
  let failures = 0;
  try {
    await waitFor(BASE, "vite preview");
    await waitFor(`http://127.0.0.1:${CDP_PORT}/json/version`, "Chrome");
    const c = await devtools();
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
    c.close();
  } finally {
    const exited = new Promise((r) => chrome.once("exit", r));
    chrome.kill();
    web.kill();
    await exited;
    rmSync(profile, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  }
  return failures ? 1 : 0;
}

process.exit(await main());
