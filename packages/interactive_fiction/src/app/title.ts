/** The title screen of a series: its key art, the content warning, and where to go next. */

import { setAmbience } from "./audio.ts";
import { app, el, esc, setStoryCss } from "./dom.ts";
import type { SeriesEntry } from "./library.ts";
import { clear, lastPlayed, load } from "./save.ts";
import { openSettings } from "./settings-ui.ts";

export function renderTitle(series: SeriesEntry): void {
  setStoryCss("");
  document.title = series.title;
  setAmbience(series.game.audio?.default ?? "silence");
  const title = series.game.title ?? {};
  const last = lastPlayed();
  const resume =
    last && last.series === series.id && series.chapters.some((c) => c.id === last.chapter)
      ? `<a class="title-button primary" href="#/${series.id}/${last.chapter}">Continuar</a>`
      : "";
  const first = series.chapters[0];
  const started = first && load(series.id, first.id);
  // Inline, so the path resolves against the page and not against the stylesheet.
  const art = title.image ? ` style="background-image: url('${esc(title.image)}')"` : "";
  const screen = el(`<main class="title-screen"${art}>
    <div class="title-shade"></div>
    <div class="title-content">
      <h1 class="title-name">${esc(series.title)}</h1>
      ${title.tagline ? `<p class="title-tagline">${esc(title.tagline)}</p>` : ""}
      <nav class="title-menu">
        ${resume}
        ${first ? `<button class="title-button${resume ? "" : " primary"}" data-new>${started ? "Nueva partida" : "Empezar"}</button>` : ""}
        <a class="title-button" href="#/capitulos/${series.id}">Capítulos</a>
        <a class="title-button" href="#/logros/${series.id}">Finales y logros</a>
        <button class="title-button" data-settings>Ajustes</button>
        ${series.about.length ? `<a class="title-button" href="#/acerca/${series.id}">Acerca de</a>` : ""}
      </nav>
      ${title.warning ? `<p class="title-warning">${esc(title.warning)}</p>` : ""}
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
