/**
 * Copy what the draft serves into public/: chapter 1's built data and images
 * (run `npm run stories` in the package first) and the generated worlds
 * listed in worlds.json (kept in worlds/, outside git).
 */

import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";

const here = dirname(new URL(import.meta.url).pathname);
const stories = join(here, "../../public/stories/samantha");
const pub = join(here, "public");
if (!existsSync(join(stories, "01.json"))) throw new Error("No built chapter 1: run `npm run stories` in packages/interactive_fiction.");
rmSync(pub, { recursive: true, force: true });
mkdirSync(pub, { recursive: true });
cpSync(join(stories, "01.json"), join(pub, "01.json"));
cpSync(join(stories, "../library.json"), join(pub, "library.json"));
// Scene images keep the path the built chapter gives them (stories/<series>/scenes/…).
cpSync(join(stories, "scenes"), join(pub, "stories/samantha/scenes"), { recursive: true });
cpSync(join(here, "worlds.json"), join(pub, "worlds.json"));
const worlds = JSON.parse(readFileSync(join(here, "worlds.json"), "utf8")) as Record<string, { splats: string; collider: string }>;
for (const w of Object.values(worlds)) {
  for (const f of [w.splats, w.collider]) {
    if (!existsSync(join(here, f))) throw new Error(`Missing ${f}: download the world first.`);
    mkdirSync(dirname(join(pub, f)), { recursive: true });
    cpSync(join(here, f), join(pub, f));
  }
}
// Home-screen icon (Cheshire's keychain, painted with view.ts) and the manifest that opens the draft full screen.
const icon = join(here, "worlds/icon-1024.png");
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
} else console.log("· no worlds/icon-1024.png: the draft ships without a home-screen icon");
console.log(`✓ draft data in ${pub}`);
