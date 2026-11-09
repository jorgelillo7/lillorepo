// Take a photo into photos/: a 1280 px JPEG, turned upright, with no metadata, because
// the site is public and a phone photo carries where it was taken. Uses macOS's sips.
//
// Usage: npm run photo -- <image> <gift-id>

import { execFileSync } from "node:child_process";
import { readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { orientation, stripMetadata } from "./jpeg.ts";

// EXIF orientation to the clockwise turn that makes the pixels upright. Mirrored
// orientations (2, 4, 5, 7) do not come out of phone cameras.
const TURN: Record<number, number> = { 1: 0, 3: 180, 6: 90, 8: 270 };

const [source, id] = process.argv.slice(2);
if (!source || !id || !/^[a-z0-9]+(?:-[a-z0-9]+)*$/.test(id)) {
  console.error("Usage: npm run photo -- <image> <gift-id>   (id: lowercase words joined by dashes)");
  process.exit(1);
}

const original = readFileSync(source);
const isJpeg = original[0] === 0xff && original[1] === 0xd8;
const turn = isJpeg ? TURN[orientation(original)] : 0;
if (turn === undefined) {
  console.error(`${source}: mirrored EXIF orientation; rotate it by hand first`);
  process.exit(1);
}

const target = join(dirname(fileURLToPath(import.meta.url)), "..", "photos", `${id}.jpg`);
const args = turn ? ["-r", String(turn)] : [];
execFileSync(
  "sips",
  [...args, "-Z", "1280", "-s", "format", "jpeg", "-s", "formatOptions", "82", source, "--out", target],
  { stdio: "ignore" },
);
const clean = stripMetadata(readFileSync(target));
writeFileSync(target, clean);

const text = Buffer.from(clean).toString("latin1");
if (text.includes("Exif") || text.includes("GPS")) {
  rmSync(target);
  console.error(`${source}: the converted photo still carries metadata; not saved`);
  process.exit(1);
}
console.log(`photos/${id}.jpg (${Math.round(clean.length / 1024)} KB). Add it to gifts.json as "${id}.jpg".`);
