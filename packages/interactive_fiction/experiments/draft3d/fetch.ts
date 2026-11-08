/**
 * Download a World Labs world that already exists (from its operation or
 * world id) into worlds/, as generate.ts would: when a generation was started
 * some other way, or its download failed.
 *
 *   node fetch.ts <scene-id> <operation-or-world-id>
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const API = "https://api.worldlabs.ai/marble/v1";
const here = dirname(new URL(import.meta.url).pathname);
const [sceneId, id] = process.argv.slice(2);
if (!sceneId || !id) throw new Error("Usage: node fetch.ts <scene-id> <operation-or-world-id>");
const key = process.env.WORLDLABS_API_KEY;
if (!key) throw new Error("Set WORLDLABS_API_KEY.");
const get = async (path: string) => {
  const r = await fetch(API + path, { headers: { "WLT-Api-Key": key } });
  return { ok: r.ok, body: await r.json() };
};

let world;
const op = await get(`/operations/${id}`);
if (op.ok) {
  let done = op.body;
  while (!done.done) {
    await new Promise((r) => setTimeout(r, 10_000));
    done = (await get(`/operations/${id}`)).body;
    if (done.error) throw new Error(JSON.stringify(done.error));
  }
  world = done.response;
} else {
  const w = await get(`/worlds/${id}`);
  if (!w.ok) throw new Error(`No operation or world ${id}.`);
  world = w.body.world ?? w.body;
}
console.log(`✓ world ${world.world_id} ${world.world_marble_url ?? ""}`);
mkdirSync(join(here, "worlds"), { recursive: true });
const urls = world.assets.splats.spz_urls;
for (const [file, url] of [
  [`${sceneId}-full.spz`, urls.full_res],
  [`${sceneId}-500k.spz`, urls["500k"]],
  [`${sceneId}-100k.spz`, urls["100k"]],
  [`${sceneId}-collider.glb`, world.assets.mesh.collider_mesh_url],
] as const) {
  if (!url) continue;
  const bytes = Buffer.from(await (await fetch(url)).arrayBuffer());
  writeFileSync(join(here, "worlds", file), bytes);
  console.log(`  worlds/${file} ${(bytes.length / 2 ** 20).toFixed(1)} MiB`);
}
