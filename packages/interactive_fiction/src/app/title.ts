/** The title screen of a series: its key art, the content warning, and where to go next. */

import { setAmbience } from "./audio.ts";
import { app, el, esc, roman, setStoryCss, shortTitle } from "./dom.ts";
import { authorLine, type SeriesEntry } from "./library.ts";
import { clear, lastPlayed, load } from "./save.ts";
import { backgroundImage } from "./picture.ts";
import { openSettings } from "./settings-ui.ts";

/** "Capítulo II · Its title", for the chapter a reader left off in. */
function chapterLabel(series: SeriesEntry, chapterId: string): string {
  const i = series.chapters.findIndex((c) => c.id === chapterId);
  return `Capítulo ${roman(i + 1)} · ${shortTitle(series.chapters[i].title)}`;
}

export function renderTitle(series: SeriesEntry): void {
  setStoryCss("");
  document.title = series.title;
  setAmbience(series.game.audio?.default ?? "silence");
  const title = series.game.title ?? {};
  const last = lastPlayed();
  const resume =
    last && last.series === series.id && series.chapters.some((c) => c.id === last.chapter)
      ? `<a class="title-button primary" href="#/${series.id}/${last.chapter}">Continuar<span class="title-button-note">${esc(
          chapterLabel(series, last.chapter),
        )}</span></a>`
      : "";
  const first = series.chapters[0];
  const started = first && load(series.id, first.id);
  // Inline, so the path resolves against the page and not against the stylesheet.
  const art = title.image ? ` style="background-image: url('${esc(title.image)}'); background-image: ${esc(backgroundImage(series.images ?? {}, title.image))}"` : "";
  const screen = el(`<main class="title-screen"${art}>
    <div class="title-shade"></div>
    <div class="title-content">
      <p class="kicker">Ficción interactiva</p>
      <h1 class="title-name">${esc(series.title)}</h1>
      ${authorLine(series)}
      ${title.tagline ? `<p class="title-tagline">${esc(title.tagline)}</p>` : ""}
      <nav class="title-menu" aria-label="${esc(series.title)}">
        ${resume}
        ${first ? `<button class="title-button${resume ? "" : " primary"}" data-new>${started ? "Nueva partida" : "Empezar"}</button>` : ""}
        <a class="title-button" href="#/capitulos/${series.id}">Capítulos</a>
        <a class="title-button" href="#/logros/${series.id}">Finales y logros</a>
        <button class="title-button" data-settings>Ajustes</button>
        ${series.about.length || series.credits.length ? `<a class="title-button" href="#/acerca/${series.id}">Créditos</a>` : ""}
      </nav>
      ${title.warning ? `<p class="title-warning">${esc(title.warning)}</p>` : ""}
      ${
        series.credits.length > 1
          ? `<a class="title-credits" href="#/acerca/${series.id}">${series.credits
              .slice(1)
              .map((c) => `${esc(c.role)}: ${esc(c.name)}`)
              .join("<br>")}</a>`
          : ""
      }
    </div></main>`);
  screen.addEventListener("click", (ev) => {
    const t = ev.target as HTMLElement;
    if (t.closest("[data-settings]")) openSettings();
    const fresh = t.closest<HTMLElement>("[data-new]");
    if (!fresh || !first) return;
    // Starting over wipes chapter 1's progress: asked in the page, since embedded viewers block confirm().
    if (started && !fresh.dataset.armed) {
      fresh.dataset.armed = "1";
      fresh.textContent = "¿Borrar la partida? Toca otra vez";
      setTimeout(() => {
        if (!fresh.isConnected) return;
        delete fresh.dataset.armed;
        fresh.textContent = "Nueva partida";
      }, 4000);
      return;
    }
    clear(series.id, first.id);
    location.hash = `#/${series.id}/${first.id}`;
  });
  app.replaceChildren(screen);
}
