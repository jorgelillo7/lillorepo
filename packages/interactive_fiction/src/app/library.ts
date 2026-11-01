/** What the build publishes about the series, and the screens that list it. */

import { chapterFile, LIBRARY_FILE, type ChapterData, type ChapterSummary, type SeriesEntry } from "../contract.ts";
import { app, el, esc, fetchJson, setStoryCss, shortTitle } from "./dom.ts";
import { load, loadCodes } from "./save.ts";

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

function status(series: SeriesEntry, chapter: ChapterSummary): string {
  const p = load(series.id, chapter.id);
  const code = loadCodes(series.id)[chapter.id];
  const earned = code ? ` · código <b>${esc(code)}</b>` : "";
  if (!p) return "Sin empezar";
  return (p.finished ? "Terminado" : "En curso") + earned;
}

/** The chapter lists of every series (or of one, with `only`). */
export function renderLibrary(only?: string): void {
  setStoryCss("");
  document.title = library.length === 1 ? library[0].title : "Historias";
  const shown = only ? library.filter((s) => s.id === only) : library;
  const back = only && library.length === 1 ? `<a class="about-link" href="#/">← Título</a>` : "";
  const blocks = shown.map((series) => {
    const items = series.chapters
      .map((c, i) => {
        const p = load(series.id, c.id);
        const verb = !p ? "Empezar" : p.finished ? "Releer" : "Continuar";
        return `<li class="chapter">
          <div class="chapter-num">${i + 1}</div>
          <div class="chapter-body">
            <div class="chapter-title">${esc(shortTitle(c.title))}${c.draft ? ' <span class="badge">Borrador</span>' : ""}</div>
            <div class="chapter-status">${status(series, c)}</div>
          </div>
          <a class="button" href="#/${series.id}/${c.id}">${verb}</a>
        </li>`;
      })
      .join("");
    const about = series.about.length ? `<a class="about-link" href="#/acerca/${series.id}">Acerca de</a>` : "";
    return `<section class="series"><h1>${esc(series.title)}</h1><ol class="chapters">${items}</ol>${about}</section>`;
  });
  app.replaceChildren(
    el(`<main class="library">${blocks.join("")}<p class="note">Tu progreso se guarda en este navegador.</p>${back}</main>`),
  );
}

export function renderAbout(seriesId: string): void {
  const series = library.find((s) => s.id === seriesId);
  if (!series) {
    location.hash = "#/";
    return;
  }
  setStoryCss("");
  const paragraphs = series.about.map((p) => `<p>${esc(p)}</p>`).join("");
  app.replaceChildren(
    el(`<main class="library about"><h1>${esc(series.title)}</h1><h2>Acerca de</h2>${paragraphs}
      <a class="button secondary" href="#/">← Volver</a></main>`),
  );
}
