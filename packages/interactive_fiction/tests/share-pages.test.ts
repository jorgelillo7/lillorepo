import { describe, expect, test } from "vitest";
import type { SeriesEntry } from "../src/contract.ts";
import { chapterMeta, imageSize, seriesMeta, sharePage, shareTags, withTags } from "../scripts/share-pages.ts";

const SITE = "https://example.test/";
const series: SeriesEntry = {
  id: "s",
  title: "The Ward",
  carry: null,
  about: [],
  credits: [{ name: "Ann Author", role: "Story", links: {} }, { name: "Dev", role: "Web", links: {} }],
  game: { title: { image: "stories/s/scenes/cover.jpg" } },
  chapters: [
    { id: "01", title: "Capitulo 1 - The Door", draft: false },
    { id: "02", title: 'Capitulo 2 - "Who" & <where>', draft: false },
    { id: "03", title: "Capitulo 3 - Unwritten", draft: true },
  ],
};

describe("link previews for a series and its chapters", () => {
  test("a series is previewed with its title, its author, its published chapters and its title picture", () => {
    expect(seriesMeta(series, SITE)).toEqual({
      url: "https://example.test/leer/s/",
      target: "../../#/",
      title: "The Ward",
      description: "The Ward, ficción interactiva de Ann Author. 2 capítulos para leer y jugar en el navegador.",
      siteName: "The Ward",
      image: "https://example.test/stories/s/scenes/cover.jpg",
    });
    expect(seriesMeta({ ...series, game: { title: { tagline: "A line of the author's" } } }, SITE).description).toBe("A line of the author's");
  });

  test("a chapter is previewed with its own title, its number, the author and the picture it opens on", () => {
    expect(chapterMeta(series, 1, SITE, "stories/s/scenes/corridor.jpg")).toEqual({
      url: "https://example.test/leer/s/02/",
      target: "../../../#/s/02",
      title: '"Who" & <where> · The Ward',
      description: "Capítulo II de The Ward, ficción interactiva de Ann Author.",
      siteName: "The Ward",
      image: "https://example.test/stories/s/scenes/corridor.jpg",
    });
    expect(chapterMeta(series, 0, SITE).image).toBe("https://example.test/stories/s/scenes/cover.jpg");
  });

  test("the page a chat app reads carries absolute Open Graph tags, escaped, and sends a person on to the reader without a script", () => {
    const html = sharePage({ ...chapterMeta(series, 1, SITE, "stories/s/scenes/corridor.jpg"), imageSize: [1600, 893] });
    expect(html).toContain(`<meta property="og:title" content="&quot;Who&quot; &amp; &lt;where&gt; · The Ward" />`);
    expect(html).toContain(`<meta property="og:url" content="https://example.test/leer/s/02/" />`);
    expect(html).toContain(`<meta property="og:image" content="https://example.test/stories/s/scenes/corridor.jpg" />`);
    expect(html).toContain(`<meta property="og:image:width" content="1600" />`);
    expect(html).toContain(`<meta name="twitter:card" content="summary_large_image" />`);
    expect(html).toContain(`<meta http-equiv="refresh" content="0; url=../../../#/s/02" />`);
    expect(html).toContain(`<a href="../../../#/s/02">Leer</a>`);
    expect(html).not.toMatch(/<script/);
    expect(html).not.toContain("<where>");
  });

  test("a page without a picture is a plain summary card", () => {
    const tags = shareTags({ url: SITE, target: "./", title: "T", description: "D", siteName: "T" });
    expect(tags).toContain(`<meta name="twitter:card" content="summary" />`);
    expect(tags).not.toContain("og:image");
  });

  test("the site's own page gets the tags once, before the end of its head", () => {
    const page = `<html><head><title>x</title></head><body></body></html>`;
    const tagged = withTags(page, shareTags(seriesMeta(series, SITE)));
    expect(tagged).toMatch(/og:title[\s\S]*<\/head><body>/);
    expect(withTags(tagged, "<meta again>")).toBe(tagged);
  });

  test("a picture's size is read from a PNG or JPEG header", () => {
    const png = Buffer.alloc(32);
    png.write("\x89PNG\r\n\x1a\n", 0, "latin1");
    png.writeUInt32BE(1024, 16);
    png.writeUInt32BE(1536, 20);
    expect(imageSize(png)).toEqual([1024, 1536]);
    const jpeg = Buffer.from([0xff, 0xd8, 0xff, 0xe0, 0x00, 0x04, 0x00, 0x00, 0xff, 0xc0, 0x00, 0x11, 0x08, 0x03, 0x7d, 0x06, 0x40, 0x03, 0, 0, 0, 0, 0, 0]);
    expect(imageSize(jpeg)).toEqual([1600, 893]);
    expect(imageSize(Buffer.from("GIF89a................................"))).toBeUndefined();
  });
});
