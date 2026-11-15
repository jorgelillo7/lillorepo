import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { explore, exploreSeries, rejectedCodes, shipProblems } from "../src/engine/explore.ts";
import { parseTwee } from "../src/engine/source.ts";

const mini = parseTwee(readFileSync(new URL("./fixtures/mini.twee", import.meta.url), "utf8"));

test("every path is played: end codes, dead ends and unreachable passages are reported", () => {
  const report = explore(mini, { endVar: "code", inputs: { name: ["Ana"] } });
  expect(report.errors).toEqual({});
  expect(Object.keys(report.endCodes).sort()).toEqual(["KEY", "LOST"]);
  expect(Object.keys(report.deadEnds)).toEqual(["Door"]);
  expect(report.unreached).toEqual(["Orphan"]);
  expect(report.truncated).toBe(false);
  expect(report.endPaths.LOST).toEqual(["Leave"]);
  expect(report.endPaths.KEY).toEqual(["Take a key", "Pick it up"]);
  expect(report.deadEndPaths.Door).toEqual(["Leave"]);
});

test("a loop between passages terminates once a state repeats", () => {
  const report = explore(mini, { endVar: "code", maxStates: 1000 });
  expect(report.states).toBeLessThan(1000);
});

test("a story whose state grows forever is cut off and says so", () => {
  const counter = parseTwee(":: Start\n(set:$n to it + 1)[[Again|Start]]\n\n:: Setup [startup]\n(set:$n to 0)");
  const report = explore(counter, { maxStates: 50 });
  expect(report.truncated).toBe(true);
  expect(report.states).toBe(50);
});

const fixture = (name: string) => parseTwee(readFileSync(new URL(`./fixtures/stories/demo/${name}`, import.meta.url), "utf8"));

test("a chapter whose every path ends, with a code where it ends with codes, has nothing to fix", () => {
  const reports = exploreSeries([fixture("01.twee"), fixture("02.twee")], { from: "code", to: "previous" });
  expect(reports.map(shipProblems)).toEqual([[], []]);
});

test("an unreachable passage, a runtime error, a cut-off exploration and an ending without a code each stop a chapter shipping", () => {
  const problems = shipProblems(explore(mini, { endVar: "code", inputs: { name: ["Ana"] } }));
  expect(problems).toEqual(["[Orphan] is unreachable"]);

  const uncoded = parseTwee(':: Start\n[[Win|A]] [[Wander|B]]\n\n:: A\n(set:$code to "WON")Done.\n\n:: B\nNothing here.\n\n:: Setup [startup]\n(set:$code to "")');
  expect(shipProblems(explore(uncoded, { endVar: "code" }))).toEqual(["1 of 2 ways to a page with nothing to click end without a code"]);

  const counter = parseTwee(":: Start\n(set:$n to it + 1)[[Again|Start]]\n\n:: Setup [startup]\n(set:$n to 0)");
  expect(shipProblems(explore(counter, { maxStates: 50 }))).toEqual([
    "exploration stopped at 50 states: the results are incomplete",
    "no path reaches an ending",
  ]);

  const report = explore(fixture("01.twee"), { endVar: "code" });
  expect(shipProblems({ ...report, errors: { Key: "boom" } })).toEqual(["runtime error in [Key]: boom"]);
});

test("a code of the previous chapter that the next treats like a wrong one is named", () => {
  const carry = { from: "code", to: "previous" };
  expect(rejectedCodes(fixture("02.twee"), carry, ["KEY", "LOST"])).toEqual([]);
  expect(rejectedCodes(fixture("02.twee"), carry, ["KEY", "GHOST"])).toEqual(["GHOST"]);
});
