/** The reader app: routes between the library, the about page and a chapter. */

import "./harlowe.css";
import "./app.css";
import { app, el } from "./dom.ts";
import { loadLibrary, renderAbout, renderLibrary } from "./library.ts";
import { closeChapter, openChapter } from "./reader.ts";

function route(): void {
  const [, seriesId, chapterId] = location.hash.replace(/^#\/?/, "#/").split("/");
  if (seriesId === "acerca" && chapterId) {
    closeChapter();
    renderAbout(chapterId);
  } else if (seriesId && chapterId) void openChapter(seriesId, chapterId);
  else {
    closeChapter();
    renderLibrary();
  }
}

async function boot(): Promise<void> {
  try {
    await loadLibrary();
  } catch {
    app.replaceChildren(el(`<main class="library"><p class="note">No hay historias publicadas.</p></main>`));
    return;
  }
  window.addEventListener("hashchange", route);
  route();
}

void boot();
