import { readFileSync } from "node:fs";
import { expect, test } from "vitest";
import { parseTwee, type Story } from "../src/engine/source.ts";
import { validate } from "../src/engine/validate.ts";

function story(text: string): Story {
  return {
    title: "t",
    start: "Start",
    format: "Harlowe",
    formatVersion: "3.3.9",
    stylesheet: "",
    passages: [
      { name: "Setup", tags: ["startup"], text: "(set:$x to 1)" },
      { name: "Start", tags: [], text },
    ],
  };
}

const errors = (text: string) => validate(story(text)).filter((i) => i.level === "error").map((i) => i.message);

test("the fixture story is clean", () => {
  const issues = validate(parseTwee(readFileSync(new URL("./fixtures/mini.twee", import.meta.url), "utf8")));
  expect(issues.filter((i) => i.level === "error")).toEqual([]);
});

test("an unsupported macro is an error, not a silent mis-render", () => {
  expect(errors("(either: 1, 2)$x")).toContain("(either:) is not supported.");
});

test("a link to a missing passage is an error, including links inside strings", () => {
  expect(errors("(set:$r to (a:'[[Go|Nowhere]]'))$r$x")).toContain('Links to "Nowhere", which does not exist.');
});

test("a variable read but never set is an error", () => {
  expect(errors("$x $typo")).toContain("$typo is read but never set.");
});

test("a changer with no hook is an error", () => {
  expect(errors("(if: $x is 1) no hook")).toContain("(if:) has no hook [ ] after it.");
});

test("a macro written in a syntax the reader does not run is refused at build", () => {
  // Harlowe's (put: value into $var) used to be accepted and then fail mid-story.
  expect(errors("(put: 1 into $x)$x")).toContain("(put:) is not supported.");
});

test("aliases are the same macro as their main name", () => {
  expect(errors("(set:$x to (array: 1))(if: $x contains 1)[ok](elseif: true)[no](text-color: red)[r]")).toEqual([]);
});

test("a datamap key set with 's counts its variable as set", () => {
  expect(errors('(set:$m to (dm:"k", 1))(set:$m\'s k to 2)$m\'s k $x')).toEqual([]);
});
