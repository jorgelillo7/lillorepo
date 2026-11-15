/**
 * What the draft's Worker may serve: the draft is on a public URL, so a built
 * library holding a chapter marked `draft` (after `npm run dev`, `build:drafts`
 * or `play` in the package) must not be copied into it.
 */

import type { SeriesEntry } from "../../src/contract.ts";

/** Every chapter of the built library still marked `draft`, as `series/chapter`. */
export function draftChapters(library: Pick<SeriesEntry, "id" | "chapters">[]): string[] {
  return library.flatMap((s) => s.chapters.filter((c) => c.draft).map((c) => `${s.id}/${c.id}`));
}

/** Throws, naming each one, when the built library holds a draft chapter. */
export function refuseDrafts(library: Pick<SeriesEntry, "id" | "chapters">[]): void {
  const drafts = draftChapters(library);
  if (!drafts.length) return;
  throw new Error(
    `Refusing to prepare the 3D draft: public/stories holds unpublished chapters (${drafts.join(", ")}).\n` +
      "Rebuild without drafts first: `npm run stories` in packages/interactive_fiction.",
  );
}
