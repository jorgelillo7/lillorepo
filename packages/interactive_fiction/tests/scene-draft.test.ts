import { describe, expect, test } from "vitest";
import type { ArtBible } from "../scripts/art-bible.ts";
import { draftScenes, type Link } from "../scripts/scene-draft.ts";

const bible: ArtBible = {
  style: "S",
  characters: {},
  locations: { hall: { name: "Hall", description: "d", sources: [] }, cell: { name: "Cell", description: "d", sources: [] } },
  images: {
    hall: { status: "generated", file: "scenes/hall.jpg", location: "hall", scene: "s", prompt: "p", passages: { "02": ["Hall", "Hall again"] } },
    "hall-night": { status: "planned", editOf: "hall", scene: "s", passages: { "02": ["Night"] } },
    cell: { status: "planned", location: "cell", scene: "s", passages: { "01": ["Cell"] } },
  },
};

const links = new Map<string, Link[]>([
  ["Hall", [{ label: "Open the door", target: "Cell" }, { label: "Wait", target: "Night" }]],
  ["Hall again", [{ label: "Try the door", target: "Cell" }, { label: "Upstairs", target: "Attic" }]],
]);

describe("drafting a chapter's scene file from the art bible", () => {
  test("one scene per image of the chapter, one unplaced hotspot per linked passage, labelled by the story", () => {
    const draft = draftScenes(bible, "02", links);
    expect(draft.passages).toEqual({ Hall: "hall", "Hall again": "hall", Night: "hall-night" });
    expect(draft.scenes.hall.hotspots).toEqual([
      { label: "Open the door", targets: ["Cell"], rect: [0, 0, 0, 0] },
      { label: "Wait", targets: ["Night"], rect: [0, 0, 0, 0] },
      { label: "Upstairs", targets: ["Attic"], rect: [0, 0, 0, 0] },
    ]);
    expect(draft.scenes.cell).toBeUndefined();
  });

  test("an edit is the same room as the image it edits, and a planned image gets its future file name", () => {
    const draft = draftScenes(bible, "02", links);
    expect(draft.scenes["hall-night"]).toMatchObject({ image: "scenes/hall-night.jpg", room: "hall" });
  });

  test("a room already named by another chapter's scene file keeps that name", () => {
    const draft = draftScenes(bible, "02", links, new Map([["scenes/hall.jpg", "207"]]));
    expect(draft.scenes.hall.room).toBe("207");
    expect(draft.scenes["hall-night"].room).toBe("207");
  });
});
