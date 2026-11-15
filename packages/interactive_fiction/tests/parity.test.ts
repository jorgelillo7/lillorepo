import { describe, expect, test } from "vitest";
import { harloweBuildFor, harloweLiteral } from "../scripts/parity.ts";

describe("writing a page's state for Harlowe", () => {
  test("every story value becomes the Harlowe literal that sets it back", () => {
    expect(harloweLiteral(true)).toBe("true");
    expect(harloweLiteral(3)).toBe("3");
    expect(harloweLiteral('say "hi"')).toBe("'say \"hi\"'");
    expect(harloweLiteral(["a", 1, ["b"]])).toBe('(a:"a",1,(a:"b"))');
    expect(harloweLiteral({ kind: "datamap", entries: { cuchillo: "aceptado", n: 2 } })).toBe('(dm:"cuchillo","aceptado","n",2)');
    expect(harloweLiteral({ kind: "hook", src: "x" })).toBe("[x]");
  });

  test("the Harlowe build to compare with is the one beside a chapter's sources", () => {
    const series = {
      sourceDir: "/repo",
      manifest: { title: "S", chapters: [{ id: "01", source: ["shared/style", "Chapter 1/src"] }, { id: "02", source: "Chapter 2/src" }] },
    };
    const only = (path: string) => (p: string) => p === path;
    expect(harloweBuildFor(series, only("/repo/Chapter 1/build/index.html"))).toBe("/repo/Chapter 1/build/index.html");
    expect(harloweBuildFor(series, only("/repo/Chapter 2/build/index.html"))).toBe("/repo/Chapter 2/build/index.html");
    expect(harloweBuildFor(series, () => false)).toBeUndefined();
  });
});
