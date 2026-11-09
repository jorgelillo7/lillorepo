/**
 * Where the draft's 3D art lives: the author's `web/3d/` (through the
 * package's `stories/samantha` link), with `worlds.json` and the files it
 * names. A file not in his repo yet — a world being tried — is read from
 * this folder's `worlds/`, which generate.ts, fetch.ts and view.ts write to.
 */

import { existsSync, readFileSync, realpathSync } from "node:fs";
import { dirname, join } from "node:path";

const here = dirname(new URL(import.meta.url).pathname);
const link = join(here, "../../stories/samantha/3d");
if (!existsSync(link)) throw new Error("No stories/samantha/3d: link the author's web/ as stories/samantha (see the package README).");

export const art = realpathSync(link);

export interface WorldFiles {
  splats: string;
  collider: string;
  picture?: string;
  figures?: { image: string }[];
  [key: string]: any;
}

export function readWorlds(): Record<string, WorldFiles> {
  return JSON.parse(readFileSync(join(art, "worlds.json"), "utf8"));
}

/** The file a `worlds.json` path names: the author's copy, else the local one. */
export function artFile(path: string): string {
  for (const dir of [art, here]) if (existsSync(join(dir, path))) return join(dir, path);
  throw new Error(`Missing ${path} in web/3d/ and in draft3d/: download the world first.`);
}
