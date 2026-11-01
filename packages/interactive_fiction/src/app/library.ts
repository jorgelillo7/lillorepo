/** What the build publishes about the series, and the screens that list it. */

import type { GameConfig } from "../engine/game.ts";
import type { SceneFile } from "../engine/scenes.ts";
import type { Story } from "../engine/source.ts";
import { app, el, esc, fetchJson, setStoryCss, shortTitle } from "./dom.ts";
import { load, loadCodes } from "./save.ts";

export type Chapter = Story & { scenes: SceneFile | null };

export interface ChapterInfo {
  id: string;
  title: string;
  draft: boolean;
}

export interface SeriesInfo {
  id: string;
  title: string;
  carry: { from: string; to: string } | null;
  about: string[];
  game: GameConfig;
  chapters: ChapterInfo[];
}

export let library: SeriesInfo[] = [];
const chapters = new Map<string, Chapter>();

export async function loadLibrary(): Promise<void> {
  library = await fetchJson<SeriesInfo[]>("stories/library.json");
}

export async function loadChapter(series: string, chapter: string): Promise<Chapter> {
  const k = `${series}/${chapter}`;
  let c = chapters.get(k);
  if (!c) {
    c = await fetchJson<Chapter>(`stories/${k}.json`);
    chapters.set(k, c);
  }
  return c;
}

function status(series: SeriesInfo, chapter: ChapterInfo): string {
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
