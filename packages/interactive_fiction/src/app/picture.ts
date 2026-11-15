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

/** A CSS `image-set()` for a background: the widest AVIF and WebP, then the original. */
export function backgroundImage(images: Record<string, ImageSet>, src: string): string {
  const set = images[src];
  const url = (path: string) => `url('${path.replace(/'/g, "%27")}')`;
  if (!set) return url(src);
  const best = (format: "avif" | "webp") => set[format].at(-1);
  const options = (["avif", "webp"] as const).flatMap((format) => (best(format) ? [`${url(best(format)![0])} type('image/${format}')`] : []));
  const original = `${url(src)} type('image/${/\.png$/i.test(src) ? "png" : "jpeg"}')`;
  return `image-set(${[...options, original].join(", ")})`;
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
