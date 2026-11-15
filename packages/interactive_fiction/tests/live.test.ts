import { describe, expect, test } from "vitest";
import type { SeriesEntry } from "../src/contract.ts";
import { contentProblems, expectedHeaders, headerProblems, pageAssets } from "../scripts/live.ts";

const library = (chapters: [id: string, draft?: boolean][]): SeriesEntry[] => [
  { id: "s", title: "S", carry: null, about: [], credits: [], game: {}, chapters: chapters.map(([id, draft]) => ({ id, title: id, draft: Boolean(draft) })) },
];

describe("the live site against the build it was deployed from", () => {
  const built = { library: library([["01"], ["02"]]), versions: { "s/01": "aaa", "s/02": "bbb" } };

  test("the same chapters at the same versions pass", () => {
    expect(contentProblems(built, structuredClone(built))).toEqual([]);
  });

  test("a chapter missing, extra, at another version or not loading is named", () => {
    const live = { library: library([["01"], ["03"]]), versions: { "s/01": "old" } };
    expect(contentProblems(built, live)).toEqual([
      "s/02 is in the build and not live",
      "s/03 is live and not in the build",
      "s/01 is live at version old, the build is aaa",
    ]);
    expect(contentProblems(built, { library: built.library, versions: { "s/01": "aaa" } })).toEqual(["s/02 is listed live and its data does not load"]);
  });

  test("a draft chapter live is a failure whatever the build holds", () => {
    const withDraft = { library: library([["01"], ["02", true]]), versions: built.versions };
    expect(contentProblems(withDraft, withDraft)).toEqual(["s/02 is live and marked draft"]);
  });

  test("a response header missing or different from the headers file is named", () => {
    const expected = expectedHeaders("# note\n/*\n  X-Frame-Options: DENY\n  Referrer-Policy: same-origin\n/other\n  X-Else: 1\n");
    expect(expected).toEqual({ "x-frame-options": "DENY", "referrer-policy": "same-origin" });
    const sent: Record<string, string> = { "x-frame-options": "SAMEORIGIN" };
    expect(headerProblems(expected, (n) => sent[n] ?? null)).toEqual([
      'response header x-frame-options is "SAMEORIGIN", expected "DENY"',
      "response header referrer-policy is missing",
    ]);
  });

  test("the files a built page loads are read from its HTML, remote and data: URLs left out", () => {
    const html = `<link rel="icon" href="data:image/svg+xml,x"><script type="module" src="./assets/a.js"></script><link rel="stylesheet" href="./assets/a.css"><a href="https://x.test/">x</a>`;
    expect(pageAssets(html)).toEqual(["./assets/a.js", "./assets/a.css"]);
  });
});
