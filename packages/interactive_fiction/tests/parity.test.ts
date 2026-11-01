import { describe, expect, test } from "vitest";
import { harloweLiteral } from "../scripts/parity.ts";

describe("writing a page's state for Harlowe", () => {
  test("every story value becomes the Harlowe literal that sets it back", () => {
    expect(harloweLiteral(true)).toBe("true");
    expect(harloweLiteral(3)).toBe("3");
    expect(harloweLiteral('say "hi"')).toBe("'say \"hi\"'");
    expect(harloweLiteral(["a", 1, ["b"]])).toBe('(a:"a",1,(a:"b"))');
    expect(harloweLiteral({ kind: "hook", src: "x" })).toBe("[x]");
  });
});
