import { describe, expect, test } from "vitest";
import {
  ambienceFor,
  conditionFor,
  documentFor,
  inventoryOf,
  isSting,
  validateGame,
  type GameConfig,
} from "../src/engine/game.ts";
import type { Story } from "../src/engine/source.ts";
import { variablesSet } from "../src/engine/validate.ts";

const story: Story = {
  title: "t",
  start: "A",
  format: "Harlowe",
  formatVersion: "3.3.9",
  stylesheet: "",
  passages: [
    { name: "Setup", tags: ["startup"], text: "(set:$calm to 4)(set:$bag to (a:))" },
    { name: "A", tags: ["floor-3"], text: "She picks up a rusty knife from the floor." },
    { name: "Diary", tags: [], text: "Page one." },
  ],
};

const config: GameConfig = {
  title: { image: "scenes/key.jpg" },
  audio: { default: "drone", rooms: { cell: "hum" }, tags: { "floor-3": "wind" }, stings: [{ chapter: "01", passage: "A" }] },
  documents: [{ chapter: "01", passage: "Diary", title: "Diary" }],
  condition: {
    variable: "calm",
    states: [
      { value: 4, label: "Normal", level: "fine" },
      { value: 1, label: "Pánico", level: "critical" },
    ],
  },
  inventory: { variable: "bag", items: { Knife: { quote: { chapter: "01", passage: "A", text: "a rusty knife" } } } },
};

describe("game helpers", () => {
  test("the condition is the author's own state for the variable's value", () => {
    expect(conditionFor(config, 1)?.label).toBe("Pánico");
    expect(conditionFor(config, 7)).toBeUndefined();
    expect(conditionFor({}, 4)).toBeUndefined();
  });

  test("the inventory is read from the story's array, and absent when the chapter has none", () => {
    expect(inventoryOf(config, { bag: ["Knife"] })).toEqual(["Knife"]);
    expect(inventoryOf(config, {})).toBeUndefined();
  });

  test("ambience comes from the room, then the passage's tags, then the default", () => {
    expect(ambienceFor(config, "cell", ["floor-3"])).toBe("hum");
    expect(ambienceFor(config, undefined, ["floor-3"])).toBe("wind");
    expect(ambienceFor(config, undefined, [])).toBe("drone");
    expect(ambienceFor({}, undefined, [])).toBe("silence");
  });

  test("stings and documents fire only on the passages configured for them", () => {
    expect(isSting(config, "01", "A")).toBe(true);
    expect(isSting(config, "01", "Diary")).toBe(false);
    expect(documentFor(config, "01", "Diary")?.title).toBe("Diary");
    expect(documentFor(config, "02", "Diary")).toBeUndefined();
  });
});

describe("game config validation", () => {
  const chapters = { "01": story };
  const vars = variablesSet(story);

  test("a consistent config passes", () => {
    expect(validateGame(config, chapters, vars, () => true)).toEqual([]);
  });

  test("missing passages, unset variables, unknown sounds, changed quotes and missing art are errors", () => {
    const broken: GameConfig = {
      title: { image: "nope.jpg" },
      audio: { default: "screams" as never, stings: [{ chapter: "01", passage: "Nowhere" }] },
      documents: [{ chapter: "02", passage: "Diary", title: "Diary" }],
      condition: { variable: "sanity", states: [] },
      inventory: { variable: "bag", items: { Knife: { quote: { chapter: "01", passage: "A", text: "a shiny knife" } } } },
    };
    expect(validateGame(broken, chapters, vars, (p) => p !== "nope.jpg")).toEqual([
      'title: image "nope.jpg" not found.',
      'audio: unknown ambience "screams".',
      'audio sting: passage "Nowhere" not found in chapter 01.',
      'document "Diary": passage "Diary" not found in chapter 02.',
      "condition: no chapter sets $sanity.",
      'inventory item "Knife": the quote is no longer in "A".',
    ]);
  });
});
