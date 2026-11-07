/**
 * Copy what the draft serves into public/: chapter 1's built data and images
 * (run `npm run stories` in the package first) and the generated worlds
 * listed in worlds.json (kept in worlds/, outside git).
 */

import { cpSync, existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { dirname, join } from "node:path";

const here = dirname(new URL(import.meta.url).pathname);
const stories = join(here, "../../public/stories/samantha");
const pub = join(here, "public");
if (!existsSync(join(stories, "01.json"))) throw new Error("No built chapter 1: run `npm run stories` in packages/interactive_fiction.");
rmSync(pub, { recursive: true, force: true });
mkdirSync(pub, { recursive: true });
cpSync(join(stories, "01.json"), join(pub, "01.json"));
cpSync(join(stories, "scenes"), join(pub, "scenes"), { recursive: true });
cpSync(join(here, "worlds.json"), join(pub, "worlds.json"));
const worlds = JSON.parse(readFileSync(join(here, "worlds.json"), "utf8")) as Record<string, { splats: string; collider: string }>;
for (const w of Object.values(worlds)) {
  for (const f of [w.splats, w.collider]) {
    if (!existsSync(join(here, f))) throw new Error(`Missing ${f}: download the world first.`);
    mkdirSync(dirname(join(pub, f)), { recursive: true });
    cpSync(join(here, f), join(pub, f));
  }
}
console.log(`✓ draft data in ${pub}`);
