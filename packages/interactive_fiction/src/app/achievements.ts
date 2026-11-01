/** Endings found and achievements earned across a series, with what is still hidden shown as "???". */

import { achievements, summarize } from "../engine/discoveries.ts";
import { app, el, esc, setStoryCss, shortTitle } from "./dom.ts";
import { library, loadChapter } from "./library.ts";
import { load, loadFound } from "./save.ts";

export async function renderAchievements(seriesId: string): Promise<void> {
  const series = library.find((s) => s.id === seriesId);
  if (!series) {
    location.hash = "#/";
    return;
  }
  setStoryCss("");
  const data = await Promise.all(series.chapters.map((c) => loadChapter(series.id, c.id)));
  const found = loadFound(series.id);
  const finished = new Set(series.chapters.filter((c) => load(series.id, c.id)?.finished).map((c) => c.id));
  const chapters = series.chapters.map((c, i) => ({ id: c.id, title: shortTitle(c.title), discoveries: data[i].discoveries }));
  const blocks = chapters
    .map((c) => {
      if (!c.discoveries) return "";
      const sum = summarize(c.discoveries, found[c.id] ?? { endings: [], passages: [] });
      const chips = sum.endings.map((e) => `<span class="ending${e ? " found" : ""}">${e ? esc(e) : "???"}</span>`).join("");
      return `<section class="ach-chapter"><h3>${esc(c.title)}</h3>
        <p>Finales: <b>${sum.endingsFound}</b> de <b>${sum.endings.length}</b> · Rincones explorados: ${sum.passagesSeen} de ${sum.passagesTotal}</p>
        <div class="endings">${chips}</div></section>`;
    })
    .join("");
  const list = achievements(chapters, found, finished)
    .map((a) => `<li class="ach${a.done ? " done" : ""}"><span class="ach-mark">${a.done ? "◆" : "◇"}</span>${esc(a.title)}</li>`)
    .join("");
  app.replaceChildren(
    el(`<main class="library achievements"><h1>${esc(series.title)}</h1><h2>Finales y logros</h2>
      ${blocks}<h3>Logros</h3><ul class="ach-list">${list}</ul>
      <a class="button secondary" href="#/">← Volver</a></main>`),
  );
}
