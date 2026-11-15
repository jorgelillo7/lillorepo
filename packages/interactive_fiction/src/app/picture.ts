/**
 * Pictures as the build encoded them: AVIF first, then WebP, each at several
 * widths for the browser to choose from, with the original as the fallback.
 * A picture the build did not encode is shown as it is.
 */

import type { ImageSet } from "../contract.ts";

const escAttr = (s: string) => s.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;");

const srcset = (variants: [string, number][]) => variants.map(([path, width]) => `${path} ${width}w`).join(", ");

/** The `<source>` elements of one picture, lightest format first. `sizes` is how wide it is shown. */
export function sources(set: ImageSet, sizes: string): string {
  return (["avif", "webp"] as const)
    .filter((format) => set[format].length)
    .map((format) => `<source type="image/${format}" srcset="${escAttr(srcset(set[format]))}" sizes="${escAttr(sizes)}">`)
    .join("");
}

/**
 * An `<img>` for `src` with the given extra attributes, inside a `<picture>` offering the encoded
 * variants when there are any. The original's pixel size goes on the `<img>`, so the page reserves
 * its place before it loads.
 */
export function picture(images: Record<string, ImageSet>, src: string, attributes: string, sizes: string): string {
  const set = images[src];
  if (!set) return `<img src="${escAttr(src)}" ${attributes}>`;
  return `<picture>${sources(set, sizes)}<img src="${escAttr(src)}" width="${set.width}" height="${set.height}" ${attributes}></picture>`;
}

/** How wide the title screen shows its picture: the whole viewport. */
export const TITLE_SIZES = "100vw";

/**
 * The attributes of a `<link rel="preload" as="image">` for the title picture of a site holding one
 * series, matching what its `<picture>` will choose (the lightest format, at TITLE_SIZES); null when
 * the site holds several series or the series has no title picture.
 */
export function titlePreload(library: { images?: Record<string, ImageSet>; game: { title?: { image?: string } } }[]): Record<string, string> | null {
  if (library.length !== 1) return null;
  const [series] = library;
  const src = series.game.title?.image;
  if (!src) return null;
  const base = { rel: "preload", as: "image", fetchpriority: "high" };
  const set = series.images?.[src];
  const format = set && (["avif", "webp"] as const).find((f) => set[f].length);
  if (!set || !format) return { ...base, href: src };
  return { ...base, imagesrcset: srcset(set[format]), imagesizes: TITLE_SIZES, type: `image/${format}` };
}

/** Wrap the pictures a passage's own markup shows (`<img src>`) with their encoded variants, in place. */
export function upgradeImages(root: ParentNode, images: Record<string, ImageSet>, sizes: string): void {
  for (const img of root.querySelectorAll<HTMLImageElement>("img[src]")) {
    const set = images[img.getAttribute("src")!];
    if (!set || img.parentElement?.tagName === "PICTURE") continue;
    const holder = document.createElement("picture");
    holder.innerHTML = sources(set, sizes);
    if (!img.hasAttribute("width")) img.width = set.width;
    if (!img.hasAttribute("height")) img.height = set.height;
    img.decoding = "async";
    img.replaceWith(holder);
    holder.appendChild(img);
  }
}
