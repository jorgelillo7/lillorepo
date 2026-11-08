/**
 * Paint a new view of a room for a world, when the scene's own picture does
 * not show what the room needs (a door to leave by), into worlds/ (outside git).
 *
 *   node view.ts <out-name> <prompt-file> <reference.jpg> [...] [--aspect 1:1] [--dry-run]
 *
 * The references are attached in order; the series' art-bible style is added
 * to the prompt. Needs GEMINI_API_KEY (paid; about US$0.12 an image).
 */

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";

const MODEL = "gemini-3.1-flash-image";
const here = dirname(new URL(import.meta.url).pathname);
const aspectAt = process.argv.indexOf("--aspect");
const aspect = aspectAt === -1 ? "16:9" : process.argv[aspectAt + 1];
const args = process.argv.slice(2).filter((a, i, all) => a !== "--dry-run" && a !== "--aspect" && all[i - 1] !== "--aspect");
const [name, promptFile, ...refs] = args;
if (!name || !promptFile || !refs.length) throw new Error("Usage: node view.ts <out-name> <prompt-file> <reference.jpg> [...] [--dry-run]");
const bible = JSON.parse(readFileSync(join(here, "../../stories/samantha/art-bible.json"), "utf8"));
const prompt = `${readFileSync(promptFile, "utf8").trim()}\n\nStyle: ${bible.style}`;
console.log(`${name}: ${refs.length} reference(s), ${MODEL}, about US$0.12\n\n${prompt}`);
if (process.argv.includes("--dry-run")) process.exit(0);

const key = process.env.GEMINI_API_KEY;
if (!key) throw new Error("Set GEMINI_API_KEY.");
const tmp = mkdtempSync(join(tmpdir(), "view-"));
const attach = (path: string, i: number) => {
  const out = join(tmp, `${i}.jpg`);
  execFileSync("sips", ["-Z", "1600", "-s", "format", "jpeg", path, "--out", out], { stdio: "ignore" });
  return { inlineData: { mimeType: "image/jpeg", data: readFileSync(out).toString("base64") } };
};
const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${MODEL}:generateContent`, {
  method: "POST",
  headers: { "x-goog-api-key": key, "Content-Type": "application/json" },
  body: JSON.stringify({
    contents: [{ parts: [...refs.map(attach), { text: prompt }] }],
    generationConfig: { responseModalities: ["IMAGE"], imageConfig: { aspectRatio: aspect, imageSize: "2K" } },
  }),
});
const data = (await res.json()) as { error?: { message?: string }; candidates?: { content?: { parts?: { inlineData?: { data: string } }[] } }[] };
const part = data.candidates?.[0]?.content?.parts?.find((p) => p.inlineData);
if (!res.ok || !part?.inlineData) throw new Error(`HTTP ${res.status}: ${data.error?.message ?? "no image"}`);
const raw = join(tmp, "raw");
writeFileSync(raw, Buffer.from(part.inlineData.data, "base64"));
const out = join(here, "worlds", `${name}.jpg`);
execFileSync("sips", ["-s", "format", "jpeg", "-s", "formatOptions", "90", raw, "--out", out], { stdio: "ignore" });
console.log(`✓ ${out}`);
