import { describe, expect, test } from "vitest";
import { composePrompt, validateBible, type ArtBible } from "../scripts/art-bible.ts";
import type { Story } from "../src/engine/source.ts";

const chapter: Story = {
  title: "t",
  start: "Cell",
  format: "Harlowe",
  formatVersion: "3.3.9",
  stylesheet: "",
  passages: [
    { name: "Cell", tags: [], text: "A small window with //three// bars.\nA girl with  striped stockings." },
  ],
};

function bible(): ArtBible {
  return {
    style: "STYLE",
    characters: {
      girl: { name: "The girl", description: "striped stockings", sources: [{ chapter: "01", passage: "Cell", text: "A girl with striped stockings." }] },
    },
    locations: {
      cell: { name: "Cell", description: "window with three bars", sources: [{ chapter: "01", passage: "Cell", text: "window with three bars" }] },
    },
    images: {
      cell: { status: "generated", file: "scenes/cell.jpg", location: "cell", scene: "empty", prompt: "p" },
      "cell-girl": { status: "planned", editOf: "cell", characters: ["girl"], scene: "she lies on the bed" },
    },
  };
}

describe("prompts", () => {
  test("a new image gets the style, its place, its characters and its shot", () => {
    const b = bible();
    b.images.cell.characters = ["girl"];
    const prompt = composePrompt(b, "cell");
    expect(prompt).toContain("STYLE");
    expect(prompt).toContain("Place: window with three bars");
    expect(prompt).toContain("The girl: striped stockings");
    expect(prompt).toContain("Shot: empty");
  });

  test("an edit names the image it changes and keeps the room, without restating the place", () => {
    const prompt = composePrompt(bible(), "cell-girl");
    expect(prompt).toContain("Edit the attached image (scenes/cell.jpg)");
    expect(prompt).not.toContain("Place:");
    expect(prompt).toContain("The girl: striped stockings");
  });
});

test("an edit that turns the room into another place carries that place's description", () => {
  const b = bible();
  b.locations.ruin = { name: "Ruin", description: "dust and yellow walls", sources: b.locations.cell.sources };
  b.images["cell-girl"].location = "ruin";
  expect(composePrompt(b, "cell-girl")).toContain("It becomes: dust and yellow walls");
});

describe("bible validation", () => {
  const chapters = { "01": chapter };

  test("a consistent bible passes; quotes match across markup and spacing", () => {
    expect(validateBible(bible(), chapters, ["scenes/cell.jpg"], () => true)).toEqual([]);
  });

  test("a quote the author has since changed asks for the description to be reviewed", () => {
    const changed = { "01": { ...chapter, passages: [{ ...chapter.passages[0], text: "A small window with four bars." }] } };
    expect(validateBible(bible(), changed, [], () => true)).toContain(
      'location "cell": the quote from "Cell" is no longer in the text — review the description.',
    );
  });

  test("an image used by a scene but missing from the bible, or generated without its prompt, is an error", () => {
    const b = bible();
    delete b.images.cell.prompt;
    const errors = validateBible(b, chapters, ["scenes/cell.jpg", "scenes/other.jpg"], () => true);
    expect(errors).toContain('image "cell": generated but the prompt used is not recorded.');
    expect(errors).toContain('scene image "scenes/other.jpg" is not in the art bible.');
  });

  test("unknown characters, places and edit bases are errors", () => {
    const b = bible();
    b.images["cell-girl"].characters = ["ghost"];
    b.images["cell-girl"].editOf = "nowhere";
    const errors = validateBible(b, chapters, [], () => true);
    expect(errors).toContain('image "cell-girl": unknown character "ghost".');
    expect(errors).toContain('image "cell-girl": edits unknown image "nowhere".');
  });
});
