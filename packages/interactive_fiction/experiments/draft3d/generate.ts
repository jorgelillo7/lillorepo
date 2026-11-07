/**
 * Generate a World Labs world from one scene image and download it into worlds/.
 *
 *   node generate.ts <scene-id> [--full] [--prompt "…"] [--dry-run]
 *
 * The image is the scene's original in the series' art-originals/, with its
 * dark frame trimmed by the same number of pixels on every edge (a framed
 * picture comes back as a painting hung in an invented room). Needs
 * WORLDLABS_API_KEY; prints the cost before spending.
 */

import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { basename, dirname, join } from "node:path";

const API = "https://api.worldlabs.ai/marble/v1";
const CROP = 0.035;
const CREDITS_PER_USD = 1250;
const PANO_FROM_IMAGE = 80;
const MODELS = { draft: { id: "marble-1.0-draft", credits: 150 }, full: { id: "marble-1.1", credits: 1500 } };

const here = dirname(new URL(import.meta.url).pathname);
const args = process.argv.slice(2);
const flag = (name: string) => args.includes(name);
const option = (name: string) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined);
const sceneId = args[0];
if (!sceneId || sceneId.startsWith("--")) throw new Error("Usage: node generate.ts <scene-id> [--full] [--prompt …] [--dry-run]");

const web = join(here, "../../stories/samantha");
const sceneFiles = ["01-scenes.json", "02-scenes.json"].map((f) => join(web, f)).filter(existsSync);
const scene = sceneFiles.map((f) => JSON.parse(readFileSync(f, "utf8")).scenes[sceneId]).find(Boolean);
if (!scene) throw new Error(`No scene "${sceneId}" in ${sceneFiles.join(", ")}.`);
const original = join(web, "art-originals", basename(scene.image));
const source = existsSync(original) ? original : join(web, scene.image);

const model = flag("--full") ? MODELS.full : MODELS.draft;
const credits = model.credits + PANO_FROM_IMAGE;
console.log(`${sceneId}: ${source} → ${model.id}, ${credits} credits ≈ $${(credits / CREDITS_PER_USD).toFixed(2)}`);
if (flag("--dry-run")) process.exit(0);

const key = process.env.WORLDLABS_API_KEY;
if (!key) throw new Error("Set WORLDLABS_API_KEY.");

// The scene's `aspect` is a ratio; the crop needs the picture's real pixels.
const sizes = execFileSync("sips", ["-g", "pixelWidth", "-g", "pixelHeight", source], { encoding: "utf8" });
const [w, h] = ["pixelWidth", "pixelHeight"].map((k) => Number(new RegExp(`${k}: (\\d+)`).exec(sizes)![1]));
const m = Math.round(w * CROP);
const cropped = join(tmpdir(), `${sceneId}-crop.jpg`);
execFileSync("sips", ["-c", String(h - 2 * m), String(w - 2 * m), source, "--out", cropped], { stdio: "ignore" });

const call = async (path: string, init?: RequestInit) => {
  const r = await fetch(API + path, { ...init, headers: { "Content-Type": "application/json", "WLT-Api-Key": key } });
  const body = await r.json();
  if (!r.ok) throw new Error(`${r.status} ${JSON.stringify(body)}`);
  return body;
};

const op = await call("/worlds:generate", {
  method: "POST",
  body: JSON.stringify({
    display_name: `lillorepo-if ${sceneId}`,
    model: model.id,
    world_prompt: {
      type: "image",
      image_prompt: { source: "data_base64", data_base64: readFileSync(cropped).toString("base64"), extension: "jpg" },
      text_prompt: option("--prompt") ?? "Interior of a run-down hospital, seen from inside the room.",
    },
  }),
});
let done = op;
while (!done.done) {
  await new Promise((r) => setTimeout(r, 10_000));
  done = await call(`/operations/${op.operation_id}`);
  if (done.error) throw new Error(JSON.stringify(done.error));
}
const world = done.response;
console.log(`✓ world ${world.world_id} (${done.cost?.total_credits} credits) ${world.world_marble_url}`);

mkdirSync(join(here, "worlds"), { recursive: true });
const assets = world.assets;
for (const [file, url] of [
  [`${sceneId}-500k.spz`, assets.splats.spz_urls["500k"]],
  [`${sceneId}-100k.spz`, assets.splats.spz_urls["100k"]],
  [`${sceneId}-collider.glb`, assets.mesh.collider_mesh_url],
] as const) {
  writeFileSync(join(here, "worlds", file), Buffer.from(await (await fetch(url)).arrayBuffer()));
  console.log(`  worlds/${file}`);
}
const crop = [m / w, m / h].map((f) => Number(f.toFixed(5)));
console.log(`Add "${sceneId}" to worlds.json (world ${world.world_id}, crop ${JSON.stringify(crop)}); fit fovY and pitch against the image.`);
