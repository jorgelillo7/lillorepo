import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";
import { Runtime } from "../src/engine/runtime.ts";
import { hotspotsFor, validateScenes, type SceneFile } from "../src/engine/scenes.ts";
import { parseTwee } from "../src/engine/source.ts";

const mini = parseTwee(readFileSync(new URL("./fixtures/mini.twee", import.meta.url), "utf8"));

const scenes: SceneFile = {
  scenes: {
    hall: {
      image: "hall.svg",
      aspect: [16, 9],
      hotspots: [
        { label: "Key", targets: ["Key"], rect: [10, 10, 10, 10] },
        { label: "Door", targets: ["Door"], rect: [50, 10, 10, 30] },
      ],
    },
  },
  passages: { Start: "hall", Key: "hall" },
};

describe("hotspots", () => {
  test("only what the passage offers is clickable: a gated link hides its hotspot", () => {
    const rt = new Runtime(mini);
    const vars = rt.start();
    // With no key yet, Start offers both "Take a key" and "Leave".
    const first = hotspotsFor(scenes.scenes.hall, rt.visit(vars, "Start").actions);
    expect(first.shown.map((h) => h.hotspot.label)).toEqual(["Key", "Door"]);
    // With a key, the (if:) drops "Leave": the door hotspot must go with it.
    vars.keys = 1;
    const later = hotspotsFor(scenes.scenes.hall, rt.visit(vars, "Start").actions);
    expect(later.shown.map((h) => h.hotspot.label)).toEqual(["Key"]);
  });

  test("actions without a hotspot stay available as buttons", () => {
    const rt = new Runtime(mini);
    const vars = rt.start();
    vars.keys = 1;
    const page = rt.visit(vars, "Key");
    const { shown, rest } = hotspotsFor(scenes.scenes.hall, page.actions);
    expect(shown).toEqual([]);
    expect(rest.map((i) => page.actions[i].label)).toEqual(["Pick it up", "Look around"]);
  });

  const door = { image: "x", aspect: [1, 1] as [number, number], hotspots: [{ label: "Door", targets: ["A", "B", "C"], rect: [0, 0, 1, 1] as [number, number, number, number] }] };

  test("a hotspot whose passage offers one of its targets leads straight there", () => {
    const { shown } = hotspotsFor(door, [{ kind: "link", label: "to B", target: "B" }]);
    expect(shown[0].actions).toEqual([0]);
  });

  test("a hotspot whose passage offers several of its targets carries them all, for a menu", () => {
    const actions = [
      { kind: "link" as const, label: "Talk", target: "X" },
      { kind: "link" as const, label: "Downstairs", target: "C" },
      { kind: "link" as const, label: "Upstairs", target: "A" },
    ];
    const { shown, rest } = hotspotsFor(door, actions);
    expect(shown[0].actions).toEqual([2, 1]);
    expect(rest).toEqual([0]);
  });
});

describe("scene validation", () => {
  test("a clean scene file passes", () => {
    expect(validateScenes(mini, scenes, () => true)).toEqual([]);
  });

  test("unknown passages, unknown targets and missing images are errors", () => {
    const broken: SceneFile = {
      scenes: { hall: { ...scenes.scenes.hall, hotspots: [{ label: "X", targets: ["Nowhere"], rect: [0, 0, 1, 1] }] } },
      passages: { Start: "hall", Ghost: "hall", Key: "cellar" },
    };
    expect(validateScenes(mini, broken, () => false)).toEqual([
      'Scene "hall": image "hall.svg" not found.',
      'Scene "hall": hotspot "X" targets "Nowhere", which is not a passage.',
      'Passage "Ghost" in the scene map does not exist.',
      'Passage "Key" uses scene "cellar", which is not defined.',
    ]);
  });

  test("a hotspot with no area yet is an error, so a drafted scene cannot ship unplaced", () => {
    const draft: SceneFile = {
      scenes: { hall: { ...scenes.scenes.hall, hotspots: [{ label: "Door", targets: ["Start"], rect: [0, 0, 0, 0] }] } },
      passages: {},
    };
    expect(validateScenes(mini, draft, () => true)).toEqual(['Scene "hall": hotspot "Door" has no area yet — place it on the image.']);
  });
});
