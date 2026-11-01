/**
 * Prints the image prompts of a series, composed from its art bible.
 *
 *   node scripts/prompts.ts <series>            every planned image
 *   node scripts/prompts.ts <series> <id> ...   those images, planned or not
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { composePrompt, type ArtBible } from "./art-bible.ts";
import { STORIES_DIR } from "./series.ts";

const [series, ...ids] = process.argv.slice(2);
if (!series) {
  console.error("usage: node scripts/prompts.ts <series> [image id ...]");
  process.exit(2);
}
const bible = JSON.parse(readFileSync(join(STORIES_DIR, series, "art-bible.json"), "utf8")) as ArtBible;
const wanted = ids.length ? ids : Object.keys(bible.images).filter((id) => bible.images[id].status === "planned");
for (const id of wanted) {
  if (!bible.images[id]) {
    console.error(`No image "${id}" in the bible.`);
    process.exit(1);
  }
  const image = bible.images[id];
  const base = image.editOf ? ` — upload ${bible.images[image.editOf].file ?? image.editOf} first` : "";
  console.log(`\n### ${id}${base}\n\n${composePrompt(bible, id)}\n`);
}
