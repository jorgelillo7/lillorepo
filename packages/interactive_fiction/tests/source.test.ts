import { readFileSync } from "node:fs";
import { describe, expect, test } from "vitest";
import { parseStory, parseTwee, parseTwineHtml } from "../src/engine/source.ts";

const mini = readFileSync(new URL("./fixtures/mini.twee", import.meta.url), "utf8");

describe("Twee 3", () => {
  test("reads title, start, tags and the stylesheet, and drops the special passages", () => {
    const story = parseTwee(mini);
    expect(story.title).toBe("Mini");
    expect(story.start).toBe("Start");
    expect(story.passages.map((p) => p.name)).not.toContain("StoryData");
    expect(story.passages.find((p) => p.name === "Setup")?.tags).toEqual(["startup"]);
    expect(story.stylesheet).toContain('tags~="scene"');
  });

  test("a story with JavaScript is refused rather than run without it", () => {
    expect(() => parseTwee(":: Script [script]\nalert(1)\n\n:: Start\nHi")).toThrow(/JavaScript/);
  });
});

describe("published Twine HTML", () => {
  const html = `<tw-storydata name="T &amp; U" startnode="2" format="Harlowe" format-version="3.3.9">
<style role="stylesheet" id="twine-user-stylesheet" type="text/twine-css">.x{}</style>
<script role="script" id="twine-user-script" type="text/twine-javascript"></script>
<tw-passagedata pid="1" name="A" tags="t1 t2">(if: $x &lt; 2)[&quot;hi&quot;]</tw-passagedata>
<tw-passagedata pid="2" name="B" tags="">[[A]]</tw-passagedata></tw-storydata>`;

  test("unescapes passages and finds the start by pid", () => {
    const story = parseTwineHtml(html);
    expect(story.title).toBe("T & U");
    expect(story.start).toBe("B");
    expect(story.passages[0]).toEqual({ name: "A", tags: ["t1", "t2"], text: '(if: $x < 2)["hi"]' });
    expect(story.stylesheet).toBe(".x{}");
  });

  test("parseStory tells the two formats apart", () => {
    expect(parseStory(html).start).toBe("B");
    expect(parseStory(mini).start).toBe("Start");
  });
});
