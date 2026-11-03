/**
 * Generates a series' planned images with the Gemini API, from its art bible:
 * the composed prompt, plus the image an edit changes, or else the bible's
 * style reference and its characters' reference images. Each result is saved
 * full size in `art-originals/`, as a 1600 px web copy in `scenes/`, and
 * registered in the bible with the prompt that made it — then it must be
 * reviewed against the bible before a scene uses it.
 *
 *   npm run art -- <series> [image id ...] [--model M] [--max N] [--note "…"] [--dry-run]
 *
 * Without ids, every planned image. The API has no free tier for image models:
 * every call is paid. GEMINI_API_KEY holds the key (never written anywhere);
 * `--max` (default 15) caps the calls of one run, `--dry-run` prints the
 * requests and their estimated cost without calling. Needs macOS `sips`.
 */

import { execFileSync } from "node:child_process";
import { existsSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { composePrompt, type ArtBible } from "./art-bible.ts";
import { STORIES_DIR } from "./series.ts";

const DEFAULT_MODEL = "gemini-3.1-flash-image";
/** Rough US$ per 2K image, to show what a run will cost before it runs. */
const COST: Record<string, number> = { "gemini-3.1-flash-image": 0.12, "gemini-3-pro-image": 0.14 };

/**
 * What to send for one image: the attached images, in order, as `read` turns
 * their series-relative paths into attachments, and the prompt. `original`
 * names the full-size original of an image, if there is one.
 */
export function imageRequest<T>(
  bible: ArtBible,
  id: string,
  read: (path: string) => T,
  original: (id: string) => string | undefined = () => undefined,
  note = "",
): { images: T[]; prompt: string } {
  const image = bible.images[id];
  const images: T[] = [];
  const lead: string[] = [];
  if (image.editOf) {
    images.push(read(original(image.editOf) ?? bible.images[image.editOf].file!));
  } else if (bible.styleReference) {
    images.push(read(bible.styleReference));
    lead.push(
      "The first attached image is another view of the same game: match its rendering style, palette, lighting and camera language exactly, but do not copy its contents.",
    );
  }
  for (const c of image.characters ?? []) {
    const reference = bible.characters[c].reference;
    if (!reference) continue;
    images.push(read(reference));
    lead.push(
      `An attached image is the author's concept art for ${bible.characters[c].name}: keep that face, hair, build and clothes, rendered in the game's style.`,
    );
  }
  const prompt = [...lead, composePrompt(bible, id), ...(note ? [note] : [])].join("\n\n");
  return { images, prompt };
}

function option(name: string): string | undefined {
  const i = process.argv.indexOf(name);
  return i === -1 ? undefined : process.argv[i + 1];
}

async function main(): Promise<number> {
  const args = process.argv.slice(2);
  const valued = new Set(["--model", "--max", "--note"]);
  const positional = args.filter((a, i) => !a.startsWith("--") && !valued.has(args[i - 1]));
  const [series, ...ids] = positional;
  if (!series) {
    console.error('usage: npm run art -- <series> [image id ...] [--model M] [--max N] [--note "…"] [--dry-run]');
    return 2;
  }
  const model = option("--model") ?? DEFAULT_MODEL;
  const max = Number(option("--max") ?? 15);
  const note = option("--note") ?? "";
  const dryRun = args.includes("--dry-run");
  const key = process.env.GEMINI_API_KEY;
  if (!dryRun && !key) {
    console.error("GEMINI_API_KEY is not set: export the key for this shell (it is never written anywhere).");
    return 2;
  }

  const dir = realpathSync(join(STORIES_DIR, series));
  const biblePath = join(dir, "art-bible.json");
  const bible = JSON.parse(readFileSync(biblePath, "utf8")) as ArtBible;
  const wanted = ids.length ? ids : Object.keys(bible.images).filter((id) => bible.images[id].status === "planned");
  for (const id of wanted) if (!bible.images[id]) throw new Error(`No image "${id}" in the bible.`);
  const run = wanted.slice(0, max);
  console.log(`${run.length} image(s) with ${model}, about US$${((COST[model] ?? 0.15) * run.length).toFixed(2)}${wanted.length > max ? ` (${wanted.length - max} left for another run: --max)` : ""}`);

  const tmp = mkdtempSync(join(tmpdir(), "if-art-"));
  const jpeg = (path: string, size: number, out: string, quality: number) =>
    execFileSync("sips", ["-Z", String(size), "-s", "format", "jpeg", "-s", "formatOptions", String(quality), path, "--out", out], { stdio: "ignore" });
  const attach = (path: string) => {
    const out = join(tmp, `${Math.random().toString(36).slice(2)}.jpg`);
    jpeg(join(dir, path), 1600, out, 85);
    return { inlineData: { mimeType: "image/jpeg", data: readFileSync(out).toString("base64") } };
  };
  const original = (id: string) => {
    const path = `art-originals/${id}.jpg`;
    return existsSync(join(dir, path)) ? path : undefined;
  };

  let failures = 0;
  try {
    for (const id of run) {
      if (dryRun) {
        const req = imageRequest(bible, id, (p) => p, original, note);
        console.log(`\n### ${id}\nattached: ${req.images.join(", ") || "nothing"}\n\n${req.prompt}`);
        continue;
      }
      const req = imageRequest(bible, id, attach, original, note);
      const body = {
        contents: [{ parts: [...req.images, { text: req.prompt }] }],
        generationConfig: { responseModalities: ["IMAGE"], imageConfig: { aspectRatio: "16:9", imageSize: "2K" } },
      };
      let saved = false;
      for (let attempt = 1; attempt <= 3 && !saved; attempt++) {
        const res = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${model}:generateContent`, {
          method: "POST",
          headers: { "x-goog-api-key": key!, "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = (await res.json()) as {
          error?: { status?: string; message?: string };
          candidates?: { content?: { parts?: { inlineData?: { data: string } }[] }; finishReason?: string }[];
        };
        // 503 is the model overloaded; anything else is not worth a second paid call.
        if (res.status === 503 && attempt < 3) {
          await new Promise((r) => setTimeout(r, 5000 * attempt));
          continue;
        }
        const part = data.candidates?.[0]?.content?.parts?.find((p) => p.inlineData);
        if (!res.ok || !part?.inlineData) {
          console.log(`✗ ${id}: ${res.ok ? `no image (${data.candidates?.[0]?.finishReason})` : `HTTP ${res.status} ${data.error?.status}: ${data.error?.message?.slice(0, 160)}`}`);
          failures++;
          break;
        }
        const raw = join(tmp, `${id}.raw`);
        writeFileSync(raw, Buffer.from(part.inlineData.data, "base64"));
        jpeg(raw, 4096, join(dir, "art-originals", `${id}.jpg`), 88);
        jpeg(raw, 1600, join(dir, "scenes", `${id}.jpg`), 78);
        bible.images[id] = {
          ...bible.images[id],
          status: "generated",
          file: `scenes/${id}.jpg`,
          prompt: `${req.prompt}\n\n(${model}, 16:9, 2K, ${req.images.length} image(s) attached.)`,
        };
        writeFileSync(biblePath, JSON.stringify(bible, null, 2) + "\n");
        console.log(`✓ ${id} → scenes/${id}.jpg — review it against the bible before a scene uses it`);
        saved = true;
      }
    }
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
  return failures ? 1 : 0;
}

if (import.meta.url === `file://${process.argv[1]}`) process.exit(await main());
