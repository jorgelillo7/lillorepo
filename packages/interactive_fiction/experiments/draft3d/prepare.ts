/**
 * Copy what the draft serves into public/: every built chapter of the series
 * and its images (run `npm run stories` in the package first) and the worlds
 * listed in the author's `web/3d/worlds.json`. A file not in his repo yet is
 * taken from this folder's `worlds/`, where new worlds are tried first.
 */

import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { art, artFile, readWorlds } from "./art.ts";
import { dirname, join } from "node:path";

const here = dirname(new URL(import.meta.url).pathname);
const stories = join(here, "../../public/stories/samantha");
const pub = join(here, "public");
if (!existsSync(join(stories, "../library.json"))) throw new Error("No built chapters: run `npm run stories` in packages/interactive_fiction.");
rmSync(pub, { recursive: true, force: true });
mkdirSync(pub, { recursive: true });
const library = JSON.parse(readFileSync(join(stories, "../library.json"), "utf8")) as { id: string; chapters: { id: string }[] }[];
const series = library.find((s) => s.id === "samantha");
if (!series) throw new Error("No samantha series in the built library.");
for (const { id } of series.chapters) cpSync(join(stories, `${id}.json`), join(pub, `${id}.json`));
cpSync(join(stories, "../library.json"), join(pub, "library.json"));
// Scene images keep the path the built chapter gives them (stories/<series>/scenes/…).
cpSync(join(stories, "scenes"), join(pub, "stories/samantha/scenes"), { recursive: true });
// The author's own images in the text (signs, the broken mirror), by the same path.
cpSync(join(stories, "resources"), join(pub, "stories/samantha/resources"), { recursive: true });
// Every build stamps worlds.json, and the page asks for each world file with that stamp: a phone that cached an older file (an app on the home screen does) gets the new one.
const worlds = readWorlds();
writeFileSync(join(pub, "worlds.json"), JSON.stringify({ ...worlds, "": { build: Date.now() } }, null, 2));
for (const w of Object.values(worlds)) {
  for (const f of [w.splats, w.collider, ...(w.figures ?? []).map((g) => g.image)]) {
    mkdirSync(dirname(join(pub, f)), { recursive: true });
    cpSync(artFile(f), join(pub, f));
  }
}
// Home-screen icon (Cheshire's keychain, painted with view.ts) and the manifest that opens the draft full screen.
const icon = join(art, "worlds/icon-1024.png");
if (existsSync(icon)) {
  for (const [name, size] of [["apple-touch-icon.png", 180], ["icon-192.png", 192], ["icon-512.png", 512], ["favicon.png", 64]] as const) {
    execFileSync("sips", ["-z", String(size), String(size), icon, "--out", join(pub, name)], { stdio: "ignore" });
  }
  writeFileSync(join(pub, "manifest.webmanifest"), JSON.stringify({
    name: "Samantha · borrador 3D",
    short_name: "Samantha",
    display: "fullscreen",
    orientation: "landscape",
    background_color: "#000000",
    theme_color: "#000000",
    start_url: "/",
    icons: [192, 512].map((s) => ({ src: `/icon-${s}.png`, sizes: `${s}x${s}`, type: "image/png" })),
  }, null, 2));
} else console.log("· no web/3d/worlds/icon-1024.png: the draft ships without a home-screen icon");
console.log(`✓ draft data in ${pub}`);
