/**
 * A first scene file for a chapter, from the art bible: one scene per image
 * that lists passages of the chapter, and on it one hotspot per passage the
 * scene's passages link to, labelled as the story labels the link. Every
 * hotspot starts with no area, which the scene validator refuses, so a draft
 * cannot ship until each one is placed on the image.
 *
 *   npm run scenes:draft -- <series> <chapter>    writes <chapter>-scenes.json
 */

import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { exploreSeries } from "../src/engine/explore.ts";
import { Runtime } from "../src/engine/runtime.ts";
import type { Hotspot, SceneFile } from "../src/engine/scenes.ts";
import type { ArtBible } from "./art-bible.ts";
import { loadSeries } from "./series.ts";

export interface Link {
  label: string;
  target: string;
}

const fileOf = (bible: ArtBible, id: string) => bible.images[id].file ?? `scenes/${id}.jpg`;

/** The room an image shows: a name another scene file already gives it, its own place, or that of the image it edits. */
function roomOf(bible: ArtBible, id: string, rooms: Map<string, string>): string | undefined {
  const image = bible.images[id];
  return rooms.get(fileOf(bible, id)) ?? image.location ?? (image.editOf ? roomOf(bible, image.editOf, rooms) : undefined);
}

/**
 * The scene file for `chapter`. `links` is every link each passage offers in
 * any state; `rooms` maps an image file to the room an existing scene file
 * already gives it, so a room keeps one name (and one sound) across chapters.
 */
export function draftScenes(bible: ArtBible, chapter: string, links: Map<string, Link[]>, rooms: Map<string, string> = new Map()): SceneFile {
  const file: SceneFile = { scenes: {}, passages: {} };
  for (const [id, image] of Object.entries(bible.images)) {
    const names = image.passages?.[chapter];
    if (!names?.length) continue;
    const path = fileOf(bible, id);
    const hotspots: Hotspot[] = [];
    for (const name of names) {
      file.passages[name] = id;
      for (const link of links.get(name) ?? []) {
        if (hotspots.some((h) => h.targets.includes(link.target))) continue;
        hotspots.push({ label: link.label, targets: [link.target], rect: [0, 0, 0, 0] });
      }
    }
    const room = roomOf(bible, id, rooms);
    file.scenes[id] = { image: path, ...(room ? { room } : {}), aspect: [16, 9], hotspots };
  }
  return file;
}

async function main(): Promise<number> {
  const [id, chapter] = process.argv.slice(2);
  if (!id || !chapter) {
    console.error("usage: npm run scenes:draft -- <series> <chapter>");
    return 2;
  }
  const series = loadSeries(id);
  const index = series.manifest.chapters.findIndex((c) => c.id === chapter);
  if (index === -1) throw new Error(`${id}: no chapter ${chapter}.`);
  const out = join(series.dir, `${chapter}-scenes.json`);
  if (existsSync(out)) {
    console.error(`${out} already exists; move it away to draft again.`);
    return 1;
  }
  const bible = JSON.parse(readFileSync(join(series.dir, "art-bible.json"), "utf8")) as ArtBible;

  const rt = new Runtime(series.stories[index]);
  const links = new Map<string, Link[]>();
  exploreSeries(series.stories.slice(0, index + 1), series.manifest.carry, (ch, passage, vars) => {
    if (ch !== index) return;
    try {
      const page = rt.visit(vars, passage);
      const known = links.get(page.passage) ?? [];
      for (const a of page.actions) {
        if (a.kind === "link" && !known.some((k) => k.target === a.target)) known.push({ label: a.label, target: a.target });
      }
      links.set(page.passage, known);
    } catch {
      // Runtime errors are the explorer's report.
    }
  });

  const rooms = new Map<string, string>();
  for (const c of series.manifest.chapters) {
    if (!c.scenes || !existsSync(join(series.dir, c.scenes))) continue;
    const scenes = JSON.parse(readFileSync(join(series.dir, c.scenes), "utf8")) as SceneFile;
    for (const s of Object.values(scenes.scenes)) if (s.room) rooms.set(s.image, s.room);
  }

  const draft = draftScenes(bible, chapter, links, rooms);
  writeFileSync(out, JSON.stringify(draft, null, 2) + "\n");
  const spots = Object.values(draft.scenes).reduce((n, s) => n + s.hotspots.length, 0);
  console.log(`✓ ${out}: ${Object.keys(draft.scenes).length} scenes, ${Object.keys(draft.passages).length} passages, ${spots} hotspots to place.`);
  console.log(`  Add "scenes": "${chapter}-scenes.json" to the chapter in series.json once the images are in.`);
  return 0;
}

if (import.meta.url === `file://${process.argv[1]}`) process.exit(await main());
