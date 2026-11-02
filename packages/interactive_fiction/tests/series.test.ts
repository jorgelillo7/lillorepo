import { describe, expect, test } from "vitest";
import { joinSources, sourceDirOf, validateCredits } from "../scripts/series.ts";
import { parseTwee } from "../src/engine/source.ts";

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

describe("credits", () => {
  test("every credit needs a name and a role, and every link an https URL", () => {
    expect(validateCredits([{ name: "A", role: "Writing", links: { GitHub: "https://github.com/a" } }])).toEqual([]);
    expect(
      validateCredits([
        { name: "", role: "", links: {} },
        { name: "B", role: "Web", links: { LinkedIn: "http://x.com", Site: "not a url" } },
      ]),
    ).toEqual([
      "credit #1: no name.",
      "credit #1: no role.",
      'credit B: link "LinkedIn" is not an https URL.',
      'credit B: link "Site" is not an https URL.',
    ]);
  });
});

describe("chapters written as Tweego sources", () => {
  test("passages, stylesheets and scripts from several files make one story, in the order given", () => {
    const twee = joinSources([
      { path: "shared/style/base.css", text: "body { color: red }" },
      { path: "fuente/_historia.twee", text: ':: StoryTitle\nT\n\n:: StoryData\n{"start": "A", "format": "Harlowe"}' },
      { path: "fuente/a.twee", text: ":: A\nHello [[B]]" },
      { path: "fuente/b.tw", text: ":: B\nBye" },
      { path: "shared/logic/.gitkeep", text: "" },
    ]);
    const story = parseTwee(twee);
    expect(story.title).toBe("T");
    expect(story.start).toBe("A");
    expect(story.stylesheet).toBe("body { color: red }");
    expect(story.passages.map((p) => p.name)).toEqual(["A", "B"]);
  });

  test("a script among the sources is refused, as story JavaScript always is", () => {
    expect(() => parseTwee(joinSources([{ path: "shared/logic/x.js", text: "alert(1)" }]))).toThrow(/JavaScript is not supported/);
  });
});
