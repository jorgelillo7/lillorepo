/**
 * Find the camera that reproduces a world's picture: the vertical field of
 * view and downward pitch to write into worlds.json, so the scene file's
 * hotspots land on their objects. Renders the world in headless Chrome (with
 * the GPU) and scores each frame against the trimmed picture.
 *
 *   node fit.ts <scene-id> [--camera x,y,z]
 *   node fit.ts <scene-id> --around      (a contact sheet of 12 views, 30° apart)
 *
 * A best score near 0.8 or above means the world grew from the picture's own
 * viewpoint; well below (0.3) means it did not, and the hotspots have to be
 * placed by hand (see the scene-3d skill). `--around` writes
 * worlds/<scene>-around.png from the camera in worlds.json: look there for
 * anything the world invented that the story does not have.
 */

import { existsSync, readFileSync, realpathSync, writeFileSync } from "node:fs";
import { basename, dirname, join } from "node:path";
import { createServer } from "vite";
import { sleep, withChrome } from "../../scripts/chrome.ts";

const PORT = 5310;
const CDP_PORT = 9451;
const here = dirname(new URL(import.meta.url).pathname);
const sceneId = process.argv[2];
const cameraArg = process.argv.includes("--camera") ? process.argv[process.argv.indexOf("--camera") + 1] : "0,0,0";
const worlds = JSON.parse(readFileSync(join(here, "worlds.json"), "utf8"));
const world = worlds[sceneId];
if (!world) throw new Error(`No "${sceneId}" in worlds.json: generate it and add it first.`);

const web = realpathSync(join(here, "../../stories/samantha"));
const scene = ["01-scenes.json", "02-scenes.json"].map((f) => join(web, f)).filter(existsSync)
  .map((f) => JSON.parse(readFileSync(f, "utf8")).scenes[sceneId]).find(Boolean);
const original = scene ? join(web, "art-originals", basename(scene.image)) : "";
const picture = world.picture ? join(here, world.picture) : existsSync(original) ? original : join(web, scene.image);

const server = await createServer({ root: here, logLevel: "silent", server: { port: PORT, strictPort: true, fs: { allow: [here, web, "../.."] } } });
await server.listen();
try {
  await withChrome(CDP_PORT, async (c) => {
    await c.send("Page.enable");
    const q = new URLSearchParams({ splats: "@fs" + join(here, world.splats), picture: "@fs" + picture, crop: world.crop.join(",") });
    await c.send("Page.navigate", { url: `http://localhost:${PORT}/fit.html?${q}` });
    for (let i = 0; i < 240 && !(await c.ev("window.ready === true")); i++) await sleep(250);
    if (c.errors.length) throw new Error(c.errors.join("\n"));
    const [x, y, z] = (world.camera ? world.camera.join(",") : cameraArg).split(",").map(Number);
    if (process.argv.includes("--around")) {
      const url = await c.ev<string>(`around(${world.fovY ?? 46}, ${world.pitch ?? 0}, ${x}, ${y}, ${z})`);
      const out = join(here, "worlds", `${sceneId}-around.png`);
      writeFileSync(out, Buffer.from(url.split(",")[1], "base64"));
      console.log(`✓ ${out}`);
      return;
    }
    const score = (fov: number, pitch: number) => c.ev<number>(`score(${fov}, ${pitch}, ${x}, ${y}, ${z})`);
    let best = { s: -1, fov: 0, pitch: 0 };
    const consider = async (fov: number, pitch: number) => {
      const s = await score(fov, pitch);
      if (s > best.s) best = { s, fov, pitch };
    };
    for (let fov = 34; fov <= 66; fov += 4) for (let pitch = 0; pitch >= -24; pitch -= 4) await consider(fov, pitch);
    const coarse = best;
    for (let fov = coarse.fov - 3; fov <= coarse.fov + 3; fov++) for (let pitch = coarse.pitch - 3; pitch <= coarse.pitch + 3; pitch++) await consider(fov, pitch);
    console.log(`${sceneId}: fovY ${best.fov}, pitch ${best.pitch} (score ${best.s.toFixed(2)})`);
    console.log(best.s >= 0.7 ? "→ write these into worlds.json; the hotspots are cast from this camera." : "→ low: the world did not grow from this picture's viewpoint; see the scene-3d skill.");
  }, { gpu: true });
} finally {
  await server.close();
}
