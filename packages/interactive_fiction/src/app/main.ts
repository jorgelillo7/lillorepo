/** The reader app: routes between the library, the about page and a chapter. */

// Order matters: each sheet may refine the ones before it.
import "./styles/harlowe.css";
import "./styles/base.css";
import "./styles/scenes.css";
import "./styles/pacing.css";
import "./styles/hud.css";
import "./styles/documents.css";
import "./styles/effects.css";
import "./styles/title.css";
import "./styles/settings.css";
import "./styles/discoveries.css";
import "./styles/book.css";
import { unlock } from "./audio.ts";
import { app, el, focusHeading } from "./dom.ts";
import { applySettings } from "./settings.ts";
import { library, loadLibrary, renderAbout, renderLibrary } from "./library.ts";
import { closeChapter, openChapter } from "./reader.ts";
import { renderTitle } from "./title.ts";
import { renderAchievements } from "./achievements.ts";

/** Show the page the hash names. A page reached by a link, not the first one, puts focus on its heading. */
function route(ev?: HashChangeEvent): void {
  const [, first, second] = location.hash.replace(/^#\/?/, "#/").split("/");
  let shown: void | Promise<void>;
  if (first === "acerca" && second) {
    closeChapter();
    shown = renderAbout(second);
  } else if (first === "logros" && second) {
    closeChapter();
    shown = renderAchievements(second);
  } else if (first === "capitulos") {
    closeChapter();
    shown = renderLibrary(second);
  } else if (first && second) {
    // A chapter puts focus on its passage itself.
    void openChapter(first, second);
    return;
  } else {
    closeChapter();
    // One series opens on its title screen; several on the list of all of them.
    shown = library.length === 1 ? renderTitle(library[0]) : renderLibrary();
  }
  if (ev) void Promise.resolve(shown).then(() => focusHeading());
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
