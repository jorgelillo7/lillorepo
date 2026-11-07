/**
 * Compares the reader with real Harlowe, passage by passage: every distinct
 * page the explorer reaches is rendered by this reader and by the Harlowe
 * engine of a Twine build, in headless Chrome, and the visible text is
 * compared line by line — line breaks included, which a word-by-word check
 * misses. Fails on any difference.
 *
 *   npm run parity -- <series> --harlowe <a Twine HTML build> [--drafts] [--max N]
 *
 * Any Harlowe 3 build works as the engine (the author's own `build/index.html`):
 * its story is replaced, for each page, by the chapter with a startup passage
 * that sets the page's state and starts on it.
 */

import { mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { exploreSeries } from "../src/engine/explore.ts";
import { Runtime, type Vars } from "../src/engine/runtime.ts";
import type { Story } from "../src/engine/source.ts";
import type { Value } from "../src/engine/values.ts";
import { sleep, withChrome, type Devtools } from "./chrome.ts";
import { loadSeries } from "./series.ts";

const CDP_PORT = 9398;
const SETUP = "__parity_setup";

function arg(name: string): string | undefined {
  const i = process.argv.indexOf(name);
  return i === -1 ? undefined : process.argv[i + 1];
}

const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;").replace(/'/g, "&#39;");

/** A Harlowe literal for a story value. */
export function harloweLiteral(v: Value): string {
  if (typeof v === "boolean" || typeof v === "number") return String(v);
  if (typeof v === "string") {
    if (!v.includes('"')) return `"${v}"`;
    if (!v.includes("'")) return `'${v}'`;
    throw new Error(`Cannot write a string with both quote kinds: ${v.slice(0, 40)}`);
  }
  if (Array.isArray(v)) return `(a:${v.map(harloweLiteral).join(",")})`;
  if (v.kind === "hook") return `[${v.src}]`;
  if (v.kind === "datamap") {
    return `(dm:${Object.entries(v.entries).flatMap(([k, x]) => [harloweLiteral(k), harloweLiteral(x)]).join(",")})`;
  }
  throw new Error(`Cannot write a ${v.kind} value as a literal.`);
}

/** The chapter as Twine story data that starts on `passage` with `vars` already set. */
function storyData(story: Story, open: string, passage: string, vars: Vars): string {
  const setup = `{${Object.entries(vars)
    .map(([k, v]) => `(set:$${k} to ${harloweLiteral(v)})`)
    .join("")}}`;
  const passages = [
    ...story.passages.map((p) => ({ ...p, tags: p.tags.filter((t) => t !== "startup") })),
    { name: SETUP, tags: ["startup"], text: setup },
  ];
  const start = passages.findIndex((p) => p.name === passage) + 1;
  const head = open.replace(/startnode="\d+"/, `startnode="${start}"`);
  const body = passages
    .map((p, i) => `<tw-passagedata pid="${i + 1}" name="${escapeHtml(p.name)}" tags="${escapeHtml(p.tags.join(" "))}" position="0,0" size="100,100">${escapeHtml(p.text)}</tw-passagedata>`)
    .join("");
  return `${head}<style role="stylesheet" id="twine-user-stylesheet" type="text/twine-css"></style><script role="script" id="twine-user-script" type="text/twine-javascript"></script>${body}</tw-storydata>`;
}

/** Visible text with one `\n` per line break; spaces collapsed, lines trimmed. Runs in the page. */
const NORMALIZE = `(root) => {
  const out = [];
  const walk = (n) => {
    if (n.nodeType === 3) { out.push(n.textContent.replace(/\\n/g, " ")); return; }
    if (n.nodeType !== 1) return;
    const t = n.tagName;
    if (t === "TW-SIDEBAR" || t === "SCRIPT" || t === "STYLE") return;
    if (t === "BR" || t === "TW-CONSECUTIVE-BR") { out.push("\\n"); return; }
    for (const c of n.childNodes) walk(c);
  };
  walk(root);
  return out.join("").replace(/[ \\t\\u00a0\\r]+/g, " ").split("\\n").map((l) => l.trim()).join("\\n").trim();
}`;

async function harloweText(c: Devtools, file: string, n: number): Promise<string> {
  // Harlowe resumes the last session from storage on load; each page must start on its own.
  await c.ev(`try { sessionStorage.clear(); localStorage.clear(); } catch {} true`);
  await c.send("Page.navigate", { url: `file://${file}?${n}` });
  let last = "";
  for (let i = 0; i < 40; i++) {
    await sleep(100);
    const now = await c.ev<string | null>(`(() => { const p = document.querySelector("tw-passage");
      const e = document.querySelector("tw-error"); if (e) return "HARLOWE ERROR: " + e.textContent;
      return p ? (${NORMALIZE})(p) : null; })()`);
    if (now !== null && now === last) return now;
    last = now ?? "";
  }
  return last;
}

function firstDifference(a: string, b: string): string {
  const la = a.split("\n");
  const lb = b.split("\n");
  const i = la.findIndex((l, n) => l !== lb[n]);
  const at = i === -1 ? la.length : i;
  const show = (lines: string[]) => lines.slice(Math.max(0, at - 1), at + 2).map((l) => `      | ${l.slice(0, 110)}`).join("\n");
  return `    line ${at + 1}\n    Harlowe:\n${show(la)}\n    reader:\n${show(lb)}`;
}

async function main(): Promise<number> {
  const id = process.argv[2];
  const engine = arg("--harlowe");
  if (!id || id.startsWith("--") || !engine) {
    console.error("usage: npm run parity -- <series> --harlowe <a Twine HTML build> [--drafts] [--max N]");
    return 2;
  }
  const max = Number(arg("--max") ?? 2000);
  const series = loadSeries(id);
  const template = readFileSync(engine, "utf8");
  const a = template.indexOf("<tw-storydata");
  const b = template.indexOf("</tw-storydata>") + "</tw-storydata>".length;
  const open = /<tw-storydata[^>]*>/.exec(template.slice(a))![0];

  // One page per distinct (shown passage, rendered text): states that render alike are compared once.
  const pages = series.stories.map(() => new Map<string, { passage: string; vars: Vars; html: string }>());
  const runtimes = series.stories.map((s) => new Runtime(s));
  exploreSeries(series.stories, series.manifest.carry, (ch, passage, vars) => {
    if (pages[ch].size >= max) return;
    try {
      const page = runtimes[ch].visit(structuredClone(vars), passage);
      const key = `${page.passage}\u0000${page.html}`;
      if (!pages[ch].has(key)) pages[ch].set(key, { passage, vars, html: page.html });
    } catch {
      // Runtime errors are the explorer's report, not this one.
    }
  });

  const dir = mkdtempSync(join(tmpdir(), "if-parity-"));
  const file = join(dir, "page.html");
  let differences = 0;
  let n = 0;
  try {
    await withChrome(CDP_PORT, async (c) => {
      for (const [i, entry] of series.manifest.chapters.entries()) {
        if (entry.draft && !process.argv.includes("--drafts")) continue;
        let same = 0;
        const diffs: string[] = [];
        for (const { passage, vars, html } of pages[i].values()) {
          writeFileSync(file, template.slice(0, a) + storyData(series.stories[i], open, passage, vars) + template.slice(b));
          const harlowe = await harloweText(c, file, n++);
          const ours = await c.ev<string>(`(() => { const d = document.createElement("div"); d.innerHTML = ${JSON.stringify(html)}; return (${NORMALIZE})(d); })()`);
          if (harlowe === ours) same++;
          else diffs.push(`  ✗ [${passage}]\n${firstDifference(harlowe, ours)}`);
        }
        differences += diffs.length;
        console.log(`${diffs.length ? "✗" : "✓"} ${id}/${entry.id}: ${same} of ${pages[i].size} pages render as in Harlowe`);
        for (const d of diffs.slice(0, 10)) console.log(d);
        if (diffs.length > 10) console.log(`  … and ${diffs.length - 10} more`);
      }
    });
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
  return differences ? 1 : 0;
}

if (import.meta.url === `file://${process.argv[1]}`) process.exit(await main());
