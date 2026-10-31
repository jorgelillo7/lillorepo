import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { explore } from "../src/engine/explore.ts";
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
