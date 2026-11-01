import { describe, expect, test } from "vitest";
import { sourceDirOf } from "../scripts/series.ts";

describe("where a series reads its chapters", () => {
  test("without a sourceRoot, from the series folder", () => {
    expect(sourceDirOf("/repo/stories/s", undefined)).toBe("/repo/stories/s");
  });

  test("a sourceRoot may be relative to the series folder, absolute, or under the home folder", () => {
    expect(sourceDirOf("/repo/stories/s", "../../author")).toBe("/repo/author");
    expect(sourceDirOf("/repo/stories/s", "/clones/author")).toBe("/clones/author");
    expect(sourceDirOf("/repo/stories/s", "~/Projects/author", "/home/me")).toBe("/home/me/Projects/author");
  });
});
