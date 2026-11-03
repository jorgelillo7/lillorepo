/**
 * The art bible of a series: one description per character and place, each
 * backed by sentences quoted from the story, and a register of every image
 * with the prompt that made it. Prompts are composed from it, never typed by
 * hand, so a character looks the same in every scene.
 */

import type { Story } from "../src/engine/source.ts";
import { quotes } from "../src/engine/text.ts";

/** A sentence from the story that a description is based on. */
export interface Quote {
  /** Chapter id as in series.json. */
  chapter: string;
  passage: string;
  text: string;
}

export interface Entry {
  name: string;
  /** English, prompt-ready. */
  description: string;
  sources: Quote[];
  /** Questions for the author about this entry, kept until answered. */
  open?: string[];
  /** An image of it under the series folder (the author's concept art), attached when an image of it is generated. */
  reference?: string;
}

export interface ImageEntry {
  status: "planned" | "generated";
  /** Path under the series folder once generated, e.g. `scenes/room.jpg`. */
  file?: string;
  location?: string;
  characters?: string[];
  /** Another image this one is an edit of: same room, same camera. */
  editOf?: string;
  /** What is in this particular shot: composition, the moment, what can be clicked. */
  scene: string;
  /** Exactly what was pasted when it was generated. */
  prompt?: string;
  /** Supplied by the story's author: no prompt of ours to record. */
  fromAuthor?: boolean;
  /** Chapter id → the passages this image is the scene of; what `npm run scenes:draft` builds from. */
  passages?: Record<string, string[]>;
}

export interface ArtBible {
  style: string;
  /** An image under the series folder whose look new images match: attached to every image that is not an edit. */
  styleReference?: string;
  characters: Record<string, Entry>;
  locations: Record<string, Entry>;
  images: Record<string, ImageEntry>;
}

/** The prompt for one image, from the style, its place, its characters and its shot. */
export function composePrompt(bible: ArtBible, id: string): string {
  const image = bible.images[id];
  const parts: string[] = [];
  if (image.editOf) {
    const base = bible.images[image.editOf];
    parts.push(
      `Edit the attached image (${base.file ?? image.editOf}). Keep exactly the same place, camera angle, furniture and lighting unless told otherwise.`,
    );
    // An edit that turns the room into another place carries that place's description.
    if (image.location && image.location !== base.location) {
      parts.push(`It becomes: ${bible.locations[image.location].description}`);
    }
  } else {
    parts.push(bible.style);
    if (image.location) parts.push(`Place: ${bible.locations[image.location].description}`);
  }
  for (const c of image.characters ?? []) {
    parts.push(`${bible.characters[c].name}: ${bible.characters[c].description}`);
  }
  parts.push(`Shot: ${image.scene}`);
  parts.push("16:9 landscape. No readable text, no UI, no watermark.");
  return parts.join("\n\n");
}

/**
 * Everything wrong with a bible, checked against the chapters it describes and
 * the images the scene files use. A quote that is no longer in its passage
 * means the author changed the text: the description must be reviewed.
 */
export function validateBible(
  bible: ArtBible,
  chapters: Record<string, Story>,
  sceneImages: string[],
  fileExists: (path: string) => boolean,
): string[] {
  const errors: string[] = [];
  for (const [kind, entries] of [
    ["character", bible.characters],
    ["location", bible.locations],
  ] as const) {
    for (const [id, entry] of Object.entries(entries)) {
      if (!entry.sources.length) errors.push(`${kind} "${id}" has no quote from the story.`);
      for (const q of entry.sources) {
        const passage = chapters[q.chapter]?.passages.find((p) => p.name === q.passage);
        if (!passage) {
          errors.push(`${kind} "${id}": passage "${q.passage}" not found in chapter ${q.chapter}.`);
        } else if (!quotes(passage.text, q.text)) {
          errors.push(`${kind} "${id}": the quote from "${q.passage}" is no longer in the text — review the description.`);
        }
      }
    }
  }
  if (bible.styleReference && !fileExists(bible.styleReference)) {
    errors.push(`style reference "${bible.styleReference}" not found.`);
  }
  for (const [kind, entries] of [
    ["character", bible.characters],
    ["location", bible.locations],
  ] as const) {
    for (const [id, entry] of Object.entries(entries)) {
      if (entry.reference && !fileExists(entry.reference)) errors.push(`${kind} "${id}": reference "${entry.reference}" not found.`);
    }
  }
  const files = new Map<string, string>();
  const claimed = new Map<string, string>();
  for (const [id, image] of Object.entries(bible.images)) {
    if (image.location && !bible.locations[image.location]) {
      errors.push(`image "${id}": unknown location "${image.location}".`);
    }
    for (const c of image.characters ?? []) {
      if (!bible.characters[c]) errors.push(`image "${id}": unknown character "${c}".`);
    }
    if (image.editOf && !bible.images[image.editOf]) errors.push(`image "${id}": edits unknown image "${image.editOf}".`);
    if (!image.editOf && !image.location) errors.push(`image "${id}": needs a location or an image to edit.`);
    if (image.status === "generated") {
      if (!image.file) errors.push(`image "${id}": generated but has no file.`);
      else if (!fileExists(image.file)) errors.push(`image "${id}": file "${image.file}" not found.`);
      if (!image.prompt && !image.fromAuthor) errors.push(`image "${id}": generated but the prompt used is not recorded.`);
    }
    if (image.file) files.set(image.file, id);
    for (const [chapter, names] of Object.entries(image.passages ?? {})) {
      for (const name of names) {
        if (!chapters[chapter]?.passages.some((p) => p.name === name)) {
          errors.push(`image "${id}": passage "${name}" not found in chapter ${chapter}.`);
        }
        const key = `${chapter}\u0000${name}`;
        const other = claimed.get(key);
        if (other) errors.push(`image "${id}": passage "${name}" (chapter ${chapter}) is already the scene of "${other}".`);
        claimed.set(key, id);
      }
    }
  }
  for (const file of new Set(sceneImages)) {
    if (!files.has(file)) errors.push(`scene image "${file}" is not in the art bible.`);
  }
  return errors;
}
