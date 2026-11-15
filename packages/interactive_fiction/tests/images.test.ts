// @vitest-environment happy-dom
import { existsSync, mkdirSync, mkdtempSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import sharp from "sharp";
import { describe, expect, test } from "vitest";
import { encodeImages, variantPath, widthsFor } from "../scripts/images.ts";
import { backgroundImage, picture, upgradeImages } from "../src/app/picture.ts";
import type { ImageSet } from "../src/contract.ts";

const room: ImageSet = {
  width: 1600,
  height: 900,
  avif: [["s/room.w640.avif", 640], ["s/room.w1600.avif", 1600]],
  webp: [["s/room.w640.webp", 640], ["s/room.w1600.webp", 1600]],
};

describe("pictures are encoded at build and offered lightest first", () => {
  test("a picture is encoded at the widths below its own and at its own, never enlarged", () => {
    expect(widthsFor(1600)).toEqual([640, 1024, 1600]);
    expect(widthsFor(1024)).toEqual([640, 1024]);
    expect(widthsFor(500)).toEqual([500]);
    expect(widthsFor(3000)).toEqual([640, 1024, 1600]);
    expect(variantPath("scenes/room.jpg", 640, "avif")).toBe("scenes/room.w640.avif");
  });

  test("the build writes AVIF and WebP beside each JPEG and PNG, smaller than the original, and lists them", async () => {
    const dir = mkdtempSync(join(tmpdir(), "if-images-"));
    mkdirSync(join(dir, "scenes"));
    const noise = Buffer.alloc(800 * 450 * 3);
    for (let i = 0; i < noise.length; i++) noise[i] = (i * 2654435761) >>> 24;
    await sharp(noise, { raw: { width: 800, height: 450, channels: 3 } }).blur(3).jpeg({ quality: 95 }).toFile(join(dir, "scenes/room.jpg"));
    await sharp({ create: { width: 64, height: 64, channels: 4, background: "#336" } }).png().toFile(join(dir, "scenes/sign.png"));

    const sets = await encodeImages(dir, "stories/s/");
    expect(Object.keys(sets)).toEqual(["stories/s/scenes/room.jpg", "stories/s/scenes/sign.png"]);
    const set = sets["stories/s/scenes/room.jpg"];
    expect([set.width, set.height]).toEqual([800, 450]);
    expect(set.avif).toEqual([["stories/s/scenes/room.w640.avif", 640], ["stories/s/scenes/room.w800.avif", 800]]);
    expect(set.webp.map(([, w]) => w)).toEqual([640, 800]);
    const original = statSync(join(dir, "scenes/room.jpg")).size;
    for (const [path] of [...set.avif, ...set.webp]) {
      const file = join(dir, path.replace("stories/s/", ""));
      expect(existsSync(file), path).toBe(true);
      expect(statSync(file).size, path).toBeLessThan(original);
    }
    expect((await sharp(join(dir, "scenes/room.w640.avif")).metadata()).format).toBe("heif");
    // A second build encodes nothing new and lists the same files.
    expect(await encodeImages(dir, "stories/s/")).toEqual(sets);
  });

  test("a scene is a picture element: AVIF, then WebP, then the original with its pixel size", () => {
    const html = picture({ "s/room.jpg": room }, "s/room.jpg", `alt=""`, "100vw");
    expect(html).toBe(
      `<picture><source type="image/avif" srcset="s/room.w640.avif 640w, s/room.w1600.avif 1600w" sizes="100vw">` +
        `<source type="image/webp" srcset="s/room.w640.webp 640w, s/room.w1600.webp 1600w" sizes="100vw">` +
        `<img src="s/room.jpg" width="1600" height="900" alt=""></picture>`,
    );
  });

  test("a picture the build did not encode is shown as it is", () => {
    expect(picture({}, "s/other.gif", `alt=""`, "100vw")).toBe(`<img src="s/other.gif" alt="">`);
    expect(backgroundImage({}, "s/other.jpg")).toBe("url('s/other.jpg')");
  });

  test("a background offers the widest AVIF and WebP before the original", () => {
    expect(backgroundImage({ "s/room.jpg": room }, "s/room.jpg")).toBe(
      "image-set(url('s/room.w1600.avif') type('image/avif'), url('s/room.w1600.webp') type('image/webp'), url('s/room.jpg') type('image/jpeg'))",
    );
  });

  test("a picture in the passage's own markup is wrapped in place, keeping its class and gaining its size", () => {
    const root = document.createElement("div");
    root.innerHTML = `<p>before</p><img src="s/room.jpg" class="mirror"><img src="s/unknown.png">`;
    upgradeImages(root, { "s/room.jpg": room }, "640px");
    const img = root.querySelector<HTMLImageElement>("img.mirror")!;
    expect(img.parentElement!.tagName).toBe("PICTURE");
    expect(img.parentElement!.querySelectorAll("source")).toHaveLength(2);
    expect([img.getAttribute("width"), img.getAttribute("height")]).toEqual(["1600", "900"]);
    expect(root.querySelector('img[src="s/unknown.png"]')!.parentElement).toBe(root);
    upgradeImages(root, { "s/room.jpg": room }, "640px");
    expect(root.querySelectorAll("picture")).toHaveLength(1);
  });
});
