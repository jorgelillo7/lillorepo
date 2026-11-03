import { describe, expect, test } from "vitest";
import { imageRequest } from "../scripts/art.ts";
import type { ArtBible } from "../scripts/art-bible.ts";

const bible: ArtBible = {
  style: "STYLE",
  styleReference: "scenes/room.jpg",
  characters: { nurse: { name: "The nurse", description: "white uniform", sources: [], reference: "../Concept Art/nurse.png" } },
  locations: { room: { name: "Room", description: "a cell", sources: [] }, hall: { name: "Hall", description: "a hall", sources: [] } },
  images: {
    room: { status: "generated", file: "scenes/room.jpg", location: "room", scene: "empty", prompt: "p" },
    hall: { status: "planned", location: "hall", characters: ["nurse"], scene: "she waits" },
    "room-note": { status: "planned", editOf: "room", scene: "add a note" },
  },
};
const read = (path: string) => `<${path}>`;

describe("asking the image model for a planned image", () => {
  test("a new image carries the style reference, the references of its characters, then the composed prompt", () => {
    const req = imageRequest(bible, "hall", read);
    expect(req.images).toEqual(["<scenes/room.jpg>", "<../Concept Art/nurse.png>"]);
    expect(req.prompt).toMatch(/^The first attached image is another view of the same game/);
    expect(req.prompt).toContain("concept art for The nurse");
    expect(req.prompt).toContain("Shot: she waits");
  });

  test("an edit carries only the image it edits, at full size when there is an original", () => {
    const withOriginal = imageRequest(bible, "room-note", read, (id) => (id === "room" ? "art-originals/room.jpg" : undefined));
    expect(withOriginal.images).toEqual(["<art-originals/room.jpg>"]);
    expect(withOriginal.prompt).toMatch(/^Edit the attached image/);
    expect(imageRequest(bible, "room-note", read).images).toEqual(["<scenes/room.jpg>"]);
  });
});
