/**
 * Link previews. A chat app that unfurls a link reads the HTML at that URL and
 * runs no script, and the reader's chapters live behind `#/…`, which never
 * reaches a server. So, after `vite build`, this writes one small static page
 * per series and per published chapter under `dist/leer/` — Open Graph tags,
 * then straight on to the chapter in the reader — and adds the series' tags to
 * the site's own page when it holds a single series. A draft never gets a page.
 *
 *   node scripts/share-pages.ts      (the last step of `npm run build`)
 *
 * SITE_URL is the public origin the absolute URLs are written with.
 */

import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { chapterFile, LIBRARY_FILE, type ChapterData, type SeriesEntry } from "../src/contract.ts";

export const DEFAULT_SITE = "https://interactive-fiction.jorgelillo.workers.dev";
/** The folder of the share pages, in the site. */
export const SHARE_DIR = "leer";

export interface ShareMeta {
  /** The page's own absolute URL. */
  url: string;
  /** Where a person lands — the reader, at the series or the chapter — relative to the page, so a preview build stays on its own origin. */
  target: string;
  title: string;
  description: string;
  siteName: string;
  /** Absolute URL of a JPEG or PNG; chat apps do not all read newer formats. */
  image?: string;
  /** What the image shows, for whoever cannot see it. */
  imageAlt?: string;
  imageSize?: [width: number, height: number];
}

const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

/** 1 → I, 4 → IV, 12 → XII. */
function roman(n: number): string {
  let out = "";
  for (const [value, mark] of [[10, "X"], [9, "IX"], [5, "V"], [4, "IV"], [1, "I"]] as const) {
    while (n >= value) {
      out += mark;
      n -= value;
    }
  }
  return out;
}

/** "Capitulo 2 - Its title" → "Its title", as the reader's lists show it. */
function shortTitle(title: string): string {
  const m = /^\s*cap[ií]tulo\s+\d+\s*[-–—:]\s*(.+)$/i.exec(title);
  return m ? m[1].trim() : title;
}

const absolute = (site: string, path: string) => `${site.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;

/** "ficción interactiva de <author>", the author being the series' first credit. */
function byline(series: SeriesEntry): string {
  const author = series.credits[0]?.name;
  return author ? `ficción interactiva de ${author}` : "ficción interactiva";
}

export function seriesMeta(series: SeriesEntry, site: string): ShareMeta {
  const chapters = series.chapters.filter((c) => !c.draft).length;
  const image = series.game.title?.image;
  return {
    url: absolute(site, `${SHARE_DIR}/${series.id}/`),
    target: "../../#/",
    title: series.title,
    description:
      series.game.title?.tagline ??
      `${series.title}, ${byline(series)}. ${chapters === 1 ? "Un capítulo" : `${chapters} capítulos`} para leer y jugar en el navegador.`,
    siteName: series.title,
    ...(image ? { image: absolute(site, image), imageAlt: `Portada de ${series.title}` } : {}),
  };
}

/** The tags of one chapter; `cover` is the picture of the scene it opens on, when it has scenes. */
export function chapterMeta(series: SeriesEntry, index: number, site: string, cover?: string): ShareMeta {
  const chapter = series.chapters[index];
  const image = cover ?? series.game.title?.image;
  return {
    url: absolute(site, `${SHARE_DIR}/${series.id}/${chapter.id}/`),
    target: `../../../#/${series.id}/${chapter.id}`,
    title: `${shortTitle(chapter.title)} · ${series.title}`,
    description: `Capítulo ${roman(index + 1)} de ${series.title}, ${byline(series)}.`,
    siteName: series.title,
    ...(image ? { image: absolute(site, image), imageAlt: `La escena con la que empieza «${shortTitle(chapter.title)}»` } : {}),
  };
}

/** The media type of a JPEG or PNG URL, which chat apps read before fetching it; undefined for anything else. */
function imageType(url: string): string | undefined {
  if (/\.jpe?g$/i.test(url)) return "image/jpeg";
  if (/\.png$/i.test(url)) return "image/png";
  return undefined;
}

/** The Open Graph and Twitter tags of a page, one per line. */
export function shareTags(meta: ShareMeta): string {
  const tags = [
    `<meta name="description" content="${esc(meta.description)}" />`,
    `<link rel="canonical" href="${esc(meta.url)}" />`,
    `<meta property="og:type" content="website" />`,
    `<meta property="og:locale" content="es_ES" />`,
    `<meta property="og:site_name" content="${esc(meta.siteName)}" />`,
    `<meta property="og:title" content="${esc(meta.title)}" />`,
    `<meta property="og:description" content="${esc(meta.description)}" />`,
    `<meta property="og:url" content="${esc(meta.url)}" />`,
  ];
  if (meta.image) {
    tags.push(`<meta property="og:image" content="${esc(meta.image)}" />`);
    const type = imageType(meta.image);
    if (type) tags.push(`<meta property="og:image:type" content="${type}" />`);
    if (meta.imageAlt) tags.push(`<meta property="og:image:alt" content="${esc(meta.imageAlt)}" />`);
    if (meta.imageSize) {
      tags.push(`<meta property="og:image:width" content="${meta.imageSize[0]}" />`, `<meta property="og:image:height" content="${meta.imageSize[1]}" />`);
    }
  }
  tags.push(
    `<meta name="twitter:card" content="${meta.image ? "summary_large_image" : "summary"}" />`,
    `<meta name="twitter:title" content="${esc(meta.title)}" />`,
    `<meta name="twitter:description" content="${esc(meta.description)}" />`,
    ...(meta.image ? [`<meta name="twitter:image" content="${esc(meta.image)}" />`] : []),
    ...(meta.image && meta.imageAlt ? [`<meta name="twitter:image:alt" content="${esc(meta.imageAlt)}" />`] : []),
  );
  return tags.join("\n    ");
}

/**
 * A page a chat app can read and a person passes straight through: the tags, a refresh to the
 * reader (the site's policy allows no inline script) and a plain link for a browser that ignores it.
 */
export function sharePage(meta: ShareMeta): string {
  return `<!doctype html>
<html lang="es">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <meta name="theme-color" content="#000000" />
    <meta name="color-scheme" content="dark" />
    <title>${esc(meta.title)}</title>
    ${shareTags(meta)}
    <meta http-equiv="refresh" content="0; url=${esc(meta.target)}" />
    <style>
      :root { color-scheme: dark; }
      body { margin: 0; min-height: 100vh; display: grid; place-items: center; background: #000; color: #e9e2c9; font: 1.1rem Georgia, serif; text-align: center; }
      a { display: inline-block; padding: 0.75rem 1.25rem; color: inherit; }
    </style>
  </head>
  <body>
    <main>
      <h1>${esc(meta.title)}</h1>
      <p>${esc(meta.description)}</p>
      <p><a href="${esc(meta.target)}">Leer</a></p>
    </main>
  </body>
</html>
`;
}

/**
 * The site's own page with a description and, when given, a series' tags, added before `</head>`,
 * and `title` as its `<title>`, so a link to the site names what the preview names. Tags already
 * there are not added twice.
 */
export function withTags(html: string, tags: string, title?: string): string {
  if (html.includes('property="og:title"')) return html;
  const titled = title ? html.replace(/<title>[^<]*<\/title>/, `<title>${esc(title)}</title>`) : html;
  return titled.replace("</head>", `  ${tags}\n  </head>`);
}

/** Width and height of a JPEG or PNG file, read from its header; undefined for anything else. */
export function imageSize(bytes: Buffer): [number, number] | undefined {
  if (bytes.length > 24 && bytes.toString("latin1", 1, 4) === "PNG") return [bytes.readUInt32BE(16), bytes.readUInt32BE(20)];
  if (bytes[0] !== 0xff || bytes[1] !== 0xd8) return undefined;
  for (let at = 2; at + 9 < bytes.length; ) {
    if (bytes[at] !== 0xff) return undefined;
    const marker = bytes[at + 1];
    const length = bytes.readUInt16BE(at + 2);
    // A start-of-frame segment holds the size; 0xC4, 0xC8 and 0xCC are other tables.
    if (marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc) {
      return [bytes.readUInt16BE(at + 7), bytes.readUInt16BE(at + 5)];
    }
    at += 2 + length;
  }
  return undefined;
}

function main(): void {
  const dist = new URL("../dist/", import.meta.url).pathname;
  const site = process.env.SITE_URL ?? DEFAULT_SITE;
  const library = JSON.parse(readFileSync(join(dist, "stories", LIBRARY_FILE), "utf8")) as SeriesEntry[];
  const sized = (meta: ShareMeta): ShareMeta => {
    const file = meta.image && join(dist, meta.image.slice(site.replace(/\/+$/, "").length + 1));
    const size = file && existsSync(file) ? imageSize(readFileSync(file)) : undefined;
    return size ? { ...meta, imageSize: size } : meta;
  };
  const write = (path: string, meta: ShareMeta) => {
    mkdirSync(join(dist, path), { recursive: true });
    writeFileSync(join(dist, path, "index.html"), sharePage(sized(meta)));
  };
  rmSync(join(dist, SHARE_DIR), { recursive: true, force: true });
  let pages = 0;
  for (const series of library) {
    write(`${SHARE_DIR}/${series.id}`, seriesMeta(series, site));
    pages++;
    series.chapters.forEach((chapter, i) => {
      if (chapter.draft) return;
      const data = JSON.parse(readFileSync(join(dist, "stories", chapterFile(series.id, chapter.id)), "utf8")) as ChapterData;
      const opening = data.scenes?.scenes[data.scenes.passages[data.start]] ?? Object.values(data.scenes?.scenes ?? {})[0];
      write(`${SHARE_DIR}/${series.id}/${chapter.id}`, chapterMeta(series, i, site, opening?.image));
      pages++;
    });
  }
  const index = join(dist, "index.html");
  const root: ShareMeta =
    library.length === 1
      ? { ...sized(seriesMeta(library[0], site)), url: absolute(site, "") }
      : { url: absolute(site, ""), target: "./", title: "Historias", siteName: "Historias", description: "Ficción interactiva para leer y jugar en el navegador." };
  writeFileSync(index, withTags(readFileSync(index, "utf8"), shareTags(root), root.title));
  console.log(`✓ ${pages} share pages in dist/${SHARE_DIR}/, link preview tags on the site's page (${site})`);
}

if (import.meta.url === `file://${process.argv[1]}`) main();
