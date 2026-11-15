/** What the build publishes about the series, and the screens that list it. */

import { chapterFile, LIBRARY_FILE, type ChapterData, type ChapterSummary, type Credit, type SeriesEntry } from "../contract.ts";
import { app, el, esc, fetchJson, roman, setStoryCss, shortTitle } from "./dom.ts";
import { load, loadCodes, loadFound } from "./save.ts";

export type { ChapterData, ChapterSummary, SeriesEntry };

export let library: SeriesEntry[] = [];
const chapters = new Map<string, ChapterData>();

export async function loadLibrary(): Promise<void> {
  library = await fetchJson<SeriesEntry[]>(`stories/${LIBRARY_FILE}`);
}

export async function loadChapter(series: string, chapter: string): Promise<ChapterData> {
  const k = `${series}/${chapter}`;
  let c = chapters.get(k);
  if (!c) {
    c = await fetchJson<ChapterData>(`stories/${chapterFile(series, chapter)}`);
    chapters.set(k, c);
  }
  return c;
}

/** Where the reader is in a chapter, in a line: not started, in progress or finished, with what was earned. */
function status(series: SeriesEntry, chapter: ChapterSummary): string {
  const p = load(series.id, chapter.id);
  if (!p) return "Sin empezar";
  const code = loadCodes(series.id)[chapter.id];
  const endings = loadFound(series.id)[chapter.id]?.endings.length ?? 0;
  const parts = [p.finished ? "Terminado" : "En curso"];
  if (code) parts.push(`código <b>${esc(code)}</b>`);
  if (endings > 1) parts.push(`${endings} finales descubiertos`);
  return parts.join(" · ");
}

/** The author of a series as a book names them under its title: the first credit. */
export function authorLine(series: SeriesEntry): string {
  const author = series.credits[0];
  return author ? `<p class="byline"><span class="byline-role">${esc(author.role)}</span><span class="byline-name">${esc(author.name)}</span></p>` : "";
}

/** One chapter of the index, a whole link: its picture, its number as a book gives it, its title and where the reader is. */
function chapterCard(series: SeriesEntry, c: ChapterSummary, i: number): string {
  const p = load(series.id, c.id);
  const verb = !p ? "Empezar" : p.finished ? "Releer" : "Continuar";
  const state = !p ? "new" : p.finished ? "done" : "open";
  const cover = c.cover ? `<img class="chapter-cover" src="${esc(c.cover)}" alt="" loading="lazy" decoding="async" width="16" height="9">` : "";
  return `<li class="chapter" data-state="${state}">
    <a class="chapter-link" href="#/${series.id}/${c.id}">
      <span class="chapter-art">${cover}</span>
      <span class="chapter-body">
        <span class="chapter-num">Capítulo ${roman(i + 1)}${c.draft ? ' <span class="badge">Borrador</span>' : ""}</span>
        <span class="chapter-title">${esc(shortTitle(c.title))}</span>
        <span class="chapter-status">${status(series, c)}</span>
        <span class="chapter-cta">${verb} <span aria-hidden="true">→</span></span>
      </span>
    </a>
  </li>`;
}

/** The index of every series (or of one, with `only`), laid out as a book's table of contents. */
export function renderLibrary(only?: string): void {
  setStoryCss("");
  const shown = only ? library.filter((s) => s.id === only) : library;
  document.title = shown.length === 1 ? `Capítulos · ${shown[0].title}` : "Historias";
  const single = library.length === 1;
  const blocks = shown.map((series) => {
    const about =
      series.about.length || series.credits.length ? `<a class="text-link" href="#/acerca/${series.id}">Créditos</a>` : "";
    return `<section class="series">
      <header class="book-head">
        <p class="kicker">Índice</p>
        <h1>${esc(series.title)}</h1>
        ${authorLine(series)}
      </header>
      <ol class="chapters">${series.chapters.map((c, i) => chapterCard(series, c, i)).join("")}</ol>
      <nav class="book-links" aria-label="${esc(series.title)}">
        ${single ? `<a class="text-link" href="#/">Portada</a>` : ""}
        <a class="text-link" href="#/logros/${series.id}">Finales y logros</a>
        ${about}
      </nav>
    </section>`;
  });
  app.replaceChildren(el(`<main class="library">${blocks.join("")}<p class="note">Tu progreso se guarda en este navegador.</p></main>`));
}

const linkList = (c: Credit) =>
  Object.entries(c.links)
    .map(([label, url]) => `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`)
    .join("");

/** Everyone credited after the author, each with their role and links. */
function creditCards(credits: Credit[]): string {
  if (!credits.length) return "";
  const card = (c: Credit) =>
    `<li class="credit"><span class="credit-role">${esc(c.role)}</span><span class="credit-name">${esc(c.name)}</span>${
      linkList(c) ? `<span class="credit-links">${linkList(c)}</span>` : ""
    }</li>`;
  return `<ul class="credits">${credits.map(card).join("")}</ul>`;
}

/** The credits page: the author first and largest, then everyone else, then how it was made. */
export function renderAbout(seriesId: string): void {
  const series = library.find((s) => s.id === seriesId);
  if (!series) {
    location.hash = "#/";
    return;
  }
  setStoryCss("");
  document.title = `Créditos · ${series.title}`;
  const [author, ...others] = series.credits;
  const lead = author
    ? `<section class="author">
        <p class="author-role">${esc(author.role)}</p>
        <h2 class="author-name">${esc(author.name)}</h2>
        ${linkList(author) ? `<p class="credit-links">${linkList(author)}</p>` : ""}
      </section>`
    : "";
  const made = series.about.length ? `<section class="made"><h2 class="kicker">Cómo se hizo</h2>${series.about.map((p) => `<p>${esc(p)}</p>`).join("")}</section>` : "";
  app.replaceChildren(
    el(`<main class="library about">
      <header class="book-head"><p class="kicker">Créditos</p><h1>${esc(series.title)}</h1></header>
      ${lead}${creditCards(others)}${made}
      <p class="colophon">Compuesto en Cormorant Garamond y Literata, tipografías de licencia abierta (SIL Open Font License).</p>
      <nav class="book-links"><a class="text-link" href="#/">Portada</a><a class="text-link" href="#/capitulos/${series.id}">Capítulos</a></nav>
    </main>`),
  );
  app.querySelector<HTMLElement>("h1")?.focus?.();
}
