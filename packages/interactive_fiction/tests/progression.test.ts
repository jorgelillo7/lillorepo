import { describe, expect, test } from "vitest";
import {
  MAX_UNDO,
  advance,
  choicesOf,
  finish,
  freshStart,
  isStale,
  outcomeOf,
  undo,
  withCarriedCode,
  withNewVariables,
} from "../src/app/progression.ts";

const link = (target: string) => ({ kind: "link" as const, label: target, target });
const carry = { from: "end", to: "previous" };

describe("moving through a chapter", () => {
  test("advancing keeps the state before each passage and the choice made on it", () => {
    let p = freshStart("A", { n: 0 });
    p = advance(p, "B", { n: 1 }, "Go to B");
    p = advance(p, "C", { n: 2 }, "Go to C");
    expect(p.passage).toBe("C");
    expect(p.vars).toEqual({ n: 2 });
    expect(p.undo.map((u) => [u.passage, u.vars.n, u.choice])).toEqual([
      ["A", 0, "Go to B"],
      ["B", 1, "Go to C"],
    ]);
    expect(choicesOf(p)).toEqual(["Go to B", "Go to C"]);
  });

  test("undo returns to the step before and forgets the choice made from it", () => {
    let p = advance(advance(freshStart("A", {}), "B", {}, "to B"), "C", {}, "to C");
    p = undo(p)!;
    expect(p.passage).toBe("B");
    expect(choicesOf(p)).toEqual(["to B"]);
    expect(p).not.toHaveProperty("choice");
    expect(undo(freshStart("A", {}))).toBeNull();
  });

  test("the history keeps the last steps only", () => {
    let p = freshStart("P0", {});
    for (let i = 1; i <= MAX_UNDO + 5; i++) p = advance(p, `P${i}`, {});
    expect(p.undo).toHaveLength(MAX_UNDO);
    expect(p.undo[0].passage).toBe("P5");
  });

  test("advancing copies the state, so later changes on the page do not leak into history", () => {
    const vars = { list: [1] };
    const p = advance(freshStart("A", {}), "B", vars);
    vars.list.push(2);
    expect(p.vars).toEqual({ list: [1] });
  });
});

describe("how a passage ends", () => {
  test("a passage with something to click or type does not end the chapter", () => {
    expect(outcomeOf({ actions: [link("B")], inputs: [] }, {}, null)).toEqual({ stuck: false, ended: false });
    expect(outcomeOf({ actions: [], inputs: ["code"] }, {}, null).stuck).toBe(false);
  });

  test("a dead end ends a chapter without codes, and one whose code is set", () => {
    expect(outcomeOf({ actions: [], inputs: [] }, {}, null)).toEqual({ stuck: true, ended: true });
    expect(outcomeOf({ actions: [], inputs: [] }, { end: "HOPE" }, carry)).toEqual({ stuck: true, ended: true, code: "HOPE" });
  });

  test("a dead end before the code is set is a path not written yet", () => {
    expect(outcomeOf({ actions: [], inputs: [] }, { end: "" }, carry)).toEqual({ stuck: true, ended: false });
  });

  test("a chapter is marked finished once, with the code it ended on", () => {
    const p = finish(freshStart("A", {}), { stuck: true, ended: true, code: "X" });
    expect(p).toMatchObject({ finished: true, code: "X" });
    expect(finish(p, { stuck: true, ended: true, code: "Y" }).code).toBe("X");
  });
});

describe("the code from the previous chapter", () => {
  test("fills the code field while it is empty, and only then", () => {
    const empty = freshStart("A", { previous: "" });
    expect(withCarriedCode(empty, carry, "HOPE").vars.previous).toBe("HOPE");
    const typed = freshStart("A", { previous: "MINE" });
    expect(withCarriedCode(typed, carry, "HOPE").vars.previous).toBe("MINE");
    expect(withCarriedCode(empty, null, "HOPE")).toBe(empty);
    expect(withCarriedCode(empty, carry, undefined)).toBe(empty);
  });
});

describe("a game saved before the chapter changed", () => {
  test("variables added since take their starting value, and saved ones are kept", () => {
    const saved = advance(freshStart("A", { old: true }), "B", { old: false }, "to B");
    const start = { old: true, estado: { kind: "datamap" as const, entries: { cuchillo: "sin_ofrecer" } } };
    const p = withNewVariables(saved, start);
    expect(p.vars).toEqual({ old: false, estado: start.estado });
    expect(p.undo[0].vars).toEqual({ old: true, estado: start.estado });
    expect(p.passage).toBe("B");
  });
});

describe("a save made before the chapter was rewritten", () => {
  const passages = new Set(["Start", "Hall", "End"]);
  const save = (passage: string, back: string[], story?: string) => ({
    ...freshStart(passage, {}, story),
    undo: back.map((p) => ({ passage: p, vars: {} })),
  });

  test("resumes when it was made on this version, whatever it points at", () => {
    expect(isStale(save("Gone", [], "v2"), passages, "v2")).toBe(false);
  });

  test("resumes after a rewrite that kept its passages", () => {
    expect(isStale(save("Hall", ["Start"], "v1"), passages, "v2")).toBe(false);
  });

  test("cannot resume when its passage was removed or renamed", () => {
    expect(isStale(save("Old hall", ["Start"], "v1"), passages, "v2")).toBe(true);
  });

  test("cannot resume when a step it could go back to is gone", () => {
    expect(isStale(save("Hall", ["Old start"], "v1"), passages, "v2")).toBe(true);
  });

  test("a save from before versions existed is checked by its passages", () => {
    expect(isStale(save("Hall", []), passages, "v2")).toBe(false);
    expect(isStale(save("Old hall", []), passages, "v2")).toBe(true);
  });

  test("a new save records the chapter's version", () => {
    expect(freshStart("Start", {}, "v2").story).toBe("v2");
  });
});
