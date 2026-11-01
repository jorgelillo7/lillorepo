import { expect, test } from "vitest";
import { achievements, discoveriesOf, summarize } from "../src/engine/discoveries.ts";
import type { ExploreReport } from "../src/engine/explore.ts";

const report = (endCodes: Record<string, number>, deadEnds: Record<string, number>): ExploreReport => ({
  states: 1,
  truncated: false,
  reached: ["A", "B", "C"],
  visited: ["A", "B"],
  unreached: [],
  deadEnds,
  endCodes,
  endPaths: {},
  errors: {},
});

test("a chapter's endings are its end codes, or its ending passages when it has none", () => {
  expect(discoveriesOf(report({ ZED: 1, ALPHA: 2 }, { End: 3 }))).toEqual({ kind: "codes", endings: ["ALPHA", "ZED"], passages: 2 });
  expect(discoveriesOf(report({}, { Fin: 2 }))).toEqual({ kind: "passages", endings: ["Fin"], passages: 2 });
});

test("the summary hides the endings not found yet and counts what was seen", () => {
  const s = summarize({ kind: "codes", endings: ["A", "B", "C"], passages: 10 }, { endings: ["B"], passages: ["x", "y", "y"] });
  expect(s).toEqual({ endings: [null, "B", null], endingsFound: 1, passagesSeen: 2, passagesTotal: 10 });
});

test("achievements come from finishing, finding every ending and seeing every passage", () => {
  const list = achievements(
    [
      { id: "01", title: "Uno", discoveries: { kind: "passages", endings: ["Fin"], passages: 2 } },
      { id: "02", title: "Dos", discoveries: { kind: "codes", endings: ["A", "B"], passages: 3 } },
    ],
    { "01": { endings: ["Fin"], passages: ["p", "q"] }, "02": { endings: ["A"], passages: ["p"] } },
    new Set(["01"]),
  );
  expect(list.map((a) => [a.id, a.done])).toEqual([
    ["01:done", true],
    ["01:explored", true],
    ["02:done", false],
    ["02:endings", false],
    ["02:explored", false],
    ["series:done", false],
  ]);
});
