/**
 * Encodes every published JPEG and PNG of a series as AVIF and WebP at the
 * widths the reader asks for, beside the original, which stays as the
 * fallback. Encoded files are kept in a cache keyed by the image's content,
 * so a build only encodes what changed.
 */

import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readdirSync, readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import sharp from "sharp";
import type { ImageSet } from "../src/contract.ts";

/** Widths offered, in CSS pixels at 1x and 2x of a phone, and the full picture for a desktop. */
export const WIDTHS = [640, 1024, 1600];
const FORMATS = { avif: { quality: 64, effort: 5 }, webp: { quality: 82, effort: 5 } } as const;
/** Bump when the widths or the encoder settings change: cached files of the old settings are then ignored. */
const SETTINGS = `v1:${JSON.stringify(FORMATS)}`;
const CACHE = join(import.meta.dirname, "../node_modules/.cache/if-images");
const SOURCE = /\.(png|jpe?g)$/i;

/** The widths to encode for a picture `width` pixels wide: those below it, and its own. Never enlarged. */
export function widthsFor(width: number, offered: number[] = WIDTHS): number[] {
  const widest = Math.min(width, Math.max(...offered));
  return [...offered.filter((w) => w < widest), widest];
}

/** `scenes/room.jpg` at 640 px as AVIF → `scenes/room.w640.avif`. */
export function variantPath(path: string, width: number, format: string): string {
  return path.replace(SOURCE, `.w${width}.${format}`);
}

function filesUnder(dir: string, base = ""): string[] {
  return readdirSync(join(dir, base)).flatMap((name) => {
    const path = base ? `${base}/${name}` : name;
    return statSync(join(dir, path)).isDirectory() ? filesUnder(dir, path) : [path];
  });
}

/**
 * Encode every JPEG and PNG under `dir` (a series' published folder) and return what was made,
 * keyed by the path the reader knows the original by (`served` + its path under `dir`).
 */
export async function encodeImages(dir: string, served: string): Promise<Record<string, ImageSet>> {
  const sets: Record<string, ImageSet> = {};
  for (const path of filesUnder(dir).filter((p) => SOURCE.test(p) && !/\.w\d+\./.test(p)).sort()) {
    const file = join(dir, path);
    const bytes = readFileSync(file);
    const digest = createHash("sha256").update(SETTINGS).update(bytes).digest("hex").slice(0, 24);
    const { width, height } = await sharp(bytes).metadata();
    if (!width || !height) continue;
    const set: ImageSet = { width, height, avif: [], webp: [] };
    for (const format of ["avif", "webp"] as const) {
      for (const w of widthsFor(width)) {
        const out = variantPath(path, w, format);
        const cached = join(CACHE, `${digest}.w${w}.${format}`);
        if (!existsSync(cached)) {
          mkdirSync(dirname(cached), { recursive: true });
          await sharp(bytes).resize({ width: w, withoutEnlargement: true })[format](FORMATS[format]).toFile(cached);
        }
        copyFileSync(cached, join(dir, out));
        set[format].push([served + out, w]);
      }
    }
    sets[served + path] = set;
  }
  return sets;
}
