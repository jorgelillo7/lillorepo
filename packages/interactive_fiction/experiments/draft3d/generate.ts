/**
 * Generate a World Labs world from one scene image and download it into worlds/.
 *
 *   node generate.ts <scene-id> [--full] [--prompt "…"] [--trim X,Y] [--image path]
 *                    [--views 90:right.jpg,180:back.jpg,270:left.jpg] [--dry-run]
 *
 * The image is the scene's original in the series' art-originals/, with its
 * dark frame trimmed by the same number of pixels on every edge (a framed
 * picture comes back as a painting hung in an invented room). Needs
 * WORLDLABS_API_KEY; prints the cost before spending. `--trim X,Y` sets the
 * pixels trimmed from each side and from top and bottom, for a picture whose
 * frame is not the usual one (letterbox bands, say). `--image` builds the world
 * from another picture of the room than the scene's own (one from view.ts).
 * `--views` adds the room's other walls (painted with view.ts) at their
 * azimuths — 90 right, 180 behind, 270 left — so the world invents nothing
 * past the picture's edges. Views go as painted (view.ts asks for no frame):
 * trimming them made World Labs' moderation refuse the request.
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
const PANO_FROM_VIEWS = 100;

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
const source = option("--image") ?? (existsSync(original) ? original : join(web, scene.image));

const model = flag("--full") ? MODELS.full : MODELS.draft;
const views = (option("--views") ?? "").split(",").filter(Boolean).map((v) => {
  const [azimuth, path] = v.split(":");
  return { azimuth: Number(azimuth), path: join(here, path) };
});
const credits = model.credits + (views.length ? PANO_FROM_VIEWS : PANO_FROM_IMAGE);
console.log(`${sceneId}: ${source}${views.map((v) => ` + ${v.azimuth}°`).join("")} → ${model.id}, ${credits} credits ≈ $${(credits / CREDITS_PER_USD).toFixed(2)}`);
if (flag("--dry-run")) process.exit(0);

const key = process.env.WORLDLABS_API_KEY;
if (!key) throw new Error("Set WORLDLABS_API_KEY.");

// The scene's `aspect` is a ratio; the crop needs the picture's real pixels.
const size = (path: string) => {
  const out = execFileSync("sips", ["-g", "pixelWidth", "-g", "pixelHeight", path], { encoding: "utf8" });
  return ["pixelWidth", "pixelHeight"].map((k) => Number(new RegExp(`${k}: (\\d+)`).exec(out)![1]));
};
const trim = (path: string, mx: number, my: number, name: string) => {
  const [pw, ph] = size(path);
  const out = join(tmpdir(), `${sceneId}-${name}.jpg`);
  execFileSync("sips", ["-c", String(ph - 2 * my), String(pw - 2 * mx), path, "--out", out], { stdio: "ignore" });
  return out;
};
const [w, h] = size(source);
const [mx, my] = option("--trim")?.split(",").map(Number) ?? [Math.round(w * CROP), Math.round(w * CROP)];
const cropped = trim(source, mx, my, "front");
const base64 = (path: string) => ({ source: "data_base64", data_base64: readFileSync(path).toString("base64"), extension: "jpg" });

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
    world_prompt: views.length
      ? {
          type: "multi-image",
          multi_image_prompt: [
            { azimuth: 0, content: base64(cropped) },
            ...views.map((v) => ({ azimuth: v.azimuth, content: base64(v.path) })),
          ],
          text_prompt: option("--prompt") ?? "Interior of a run-down hospital room.",
        }
      : {
          type: "image",
          image_prompt: base64(cropped),
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
  [`${sceneId}-full.spz`, assets.splats.spz_urls.full_res],
  [`${sceneId}-500k.spz`, assets.splats.spz_urls["500k"]],
  [`${sceneId}-100k.spz`, assets.splats.spz_urls["100k"]],
  [`${sceneId}-collider.glb`, assets.mesh.collider_mesh_url],
] as const) {
  if (!url) continue;
  const bytes = Buffer.from(await (await fetch(url)).arrayBuffer());
  writeFileSync(join(here, "worlds", file), bytes);
  console.log(`  worlds/${file} ${(bytes.length / 2 ** 20).toFixed(1)} MiB`);
}
const crop = [mx / w, my / h].map((f) => Number(f.toFixed(5)));
console.log(`Add "${sceneId}" to the author's web/3d/worlds.json (world ${world.world_id}, crop ${JSON.stringify(crop)}); fit fovY and pitch against the image.`);
