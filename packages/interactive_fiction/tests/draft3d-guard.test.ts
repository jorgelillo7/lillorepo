import { describe, expect, test } from "vitest";
import { draftChapters, refuseDrafts } from "../experiments/draft3d/draft-guard.ts";

const chapter = (id: string, draft = false) => ({ id, title: id, draft });

describe("what the 3D draft's public preview may serve", () => {
  test("a built library of published chapters is prepared", () => {
    const library = [{ id: "s", chapters: [chapter("01"), chapter("02")] }];
    expect(draftChapters(library)).toEqual([]);
    expect(() => refuseDrafts(library)).not.toThrow();
  });

  test("a built library holding a draft chapter is refused, naming it", () => {
    const library = [
      { id: "s", chapters: [chapter("01"), chapter("03", true)] },
      { id: "t", chapters: [chapter("01", true)] },
    ];
    expect(draftChapters(library)).toEqual(["s/03", "t/01"]);
    expect(() => refuseDrafts(library)).toThrow(/s\/03, t\/01/);
  });
});
