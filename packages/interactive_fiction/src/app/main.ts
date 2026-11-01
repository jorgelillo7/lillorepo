/** The reader app: routes between the library, the about page and a chapter. */

import "./harlowe.css";
import "./app.css";
import { unlock } from "./audio.ts";
import { app, el } from "./dom.ts";
import { applySettings } from "./settings.ts";
import { library, loadLibrary, renderAbout, renderLibrary } from "./library.ts";
import { closeChapter, openChapter } from "./reader.ts";
import { renderTitle } from "./title.ts";

function route(): void {
  const [, first, second] = location.hash.replace(/^#\/?/, "#/").split("/");
  if (first === "acerca" && second) {
    closeChapter();
    renderAbout(second);
  } else if (first === "capitulos") {
    closeChapter();
    renderLibrary(second);
  } else if (first && second) void openChapter(first, second);
  else {
    closeChapter();
    // One series opens on its title screen; several on the list of all of them.
    if (library.length === 1) renderTitle(library[0]);
    else renderLibrary();
  }
}

async function boot(): Promise<void> {
  applySettings();
  // Browsers start audio only after a gesture: the first tap or key unlocks it.
  for (const type of ["pointerdown", "keydown"]) {
    window.addEventListener(type, unlock, { capture: true, passive: true });
  }
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
