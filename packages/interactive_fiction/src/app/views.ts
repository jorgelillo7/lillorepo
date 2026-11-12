/** The reader's HTML: toolbar, page layouts and end-of-chapter panels, from the data they show. */

import type { SeriesEntry } from "../contract.ts";
import { summarize, type ChapterDiscoveries, type Found } from "../engine/discoveries.ts";
import type { ConditionState } from "../engine/game.ts";
import type { Action } from "../engine/runtime.ts";
import type { Scene, ShownHotspot } from "../engine/scenes.ts";
import { esc, shortTitle } from "./dom.ts";
import { statusButton } from "./hud.ts";
import { choicesOf, type Progress } from "./progression.ts";

export interface ToolbarState {
  series: SeriesEntry;
  title: string;
  canUndo: boolean;
  /** Undefined when the chapter has no scenes, so no mode to switch. */
  gameMode?: boolean;
  muted: boolean;
  condition?: ConditionState;
  items?: string[];
}

export function toolbar(t: ToolbarState): string {
  const mode = t.gameMode === undefined ? "" : `<button class="tool" data-tool="mode">${t.gameMode ? "📖 Texto" : "🎮 Juego"}</button>`;
  return `<nav class="toolbar">
    <a class="tool" href="#/capitulos/${t.series.id}">← Capítulos</a>
    <span class="tool-title">${esc(shortTitle(t.title))}</span>
    ${statusButton(t.condition, t.items)}
    ${mode}
    <button class="tool" data-tool="mute" aria-label="Sonido">${t.muted ? "🔇" : "🔊"}</button>
    <button class="tool" data-tool="settings" aria-label="Ajustes">⚙</button>
    <button class="tool" data-tool="undo" ${t.canUndo ? "" : "disabled"}>↶ Atrás</button>
    <button class="tool" data-tool="restart">⟲ Reiniciar</button>
  </nav>`;
}

export function passageHtml(tags: string[], html: string): string {
  const t = esc(tags.join(" "));
  return `<tw-story tags="${t}"><tw-passage tags="${t}">${html}</tw-passage></tw-story>`;
}

export function textPage(bar: string, passage: string, footer: string): string {
  return `<div class="reader">${bar}${passage}${footer}</div>`;
}

export function documentPage(bar: string, title: string, passage: string, footer: string): string {
  return `<div class="reader doc-reader">${bar}
    <div class="doc-overlay"><div class="doc-sheet"><h2 class="doc-title">${esc(title)}</h2>${passage}${footer}</div></div></div>`;
}

/** The picture and its clickable areas. `seen` dims areas leading only to places already visited. */
export function stage(scene: Scene, shown: ShownHotspot[], actions: Action[], seen: Set<string>): string {
  const targetOf = (i: number) => (actions[i] as { target: string }).target;
  const spots = shown
    .map(({ hotspot, actions: mine, view }, n) => {
      const [x, y, w, h] = hotspot.rect;
      const visited = mine.every((i) => seen.has(targetOf(i))) ? " visited" : "";
      const box = `left:${x}%;top:${y}%;width:${w}%;height:${h}%`;
      const label = `<span class="hotspot-label">${esc(hotspot.label)}</span>`;
      if (view) {
        // Stepping through to another picture; `data-reaches` names the choices waiting there.
        const reaches = esc(JSON.stringify(mine.map((i) => actions[i].label)));
        return `<button class="hotspot is-view${visited}" data-view="${esc(view)}" data-reaches="${reaches}" aria-label="${esc(hotspot.label)}" style="${box}">${label}</button>`;
      }
      if (mine.length === 1) {
        const i = mine[0];
        return `<button class="hotspot${visited}" data-action="${i}" data-choice="${esc(actions[i].label)}" aria-label="${esc(hotspot.label)}" style="${box}">${label}</button>`;
      }
      // Several ways through one object: a menu, placed beside it when it opens (the reader fits it in the picture).
      const options = mine
        .map((i) => `<button class="hotspot-option${seen.has(targetOf(i)) ? " visited" : ""}" role="menuitem" data-action="${i}" data-choice="${esc(actions[i].label)}">${esc(actions[i].label)}</button>`)
        .join("");
      return `<button class="hotspot has-menu${visited}" data-menu="${n}" aria-haspopup="menu" aria-expanded="false" aria-label="${esc(hotspot.label)}" style="${box}">${label}</button>
        <div class="hotspot-menu" role="menu" data-menu-of="${n}" hidden>${options}</div>`;
    })
    .join("");
  const [aw, ah] = scene.aspect;
  return `<div class="stage" style="--ar:${aw / ah}"><img src="${esc(scene.image)}" alt="" draggable="false">${spots}</div>`;
}

/** The scene with its clickable areas beside the text. */
export function scenePage(
  bar: string,
  scene: Scene,
  shown: ShownHotspot[],
  actions: Action[],
  seen: Set<string>,
  passage: string,
  footer: string,
): string {
  return `<div class="reader game">${bar}
    <div class="game-layout">
      <div class="stage-wrap">${stage(scene, shown, actions, seen)}</div>
      <section class="panel">${passage}${footer}</section>
    </div></div>`;
}

/** A save the chapter can no longer resume: what happened, and the way on. */
export function chapterChangedPage(): string {
  return `<main class="library chapter-changed">
    <h1 tabindex="-1">El capítulo ha cambiado</h1>
    <p class="note">El autor ha reescrito este capítulo desde tu última partida y el punto donde la dejaste ya no existe.
      Empiézalo de nuevo: tus códigos, los demás capítulos y lo que has descubierto se conservan.</p>
    <button class="button" data-restart-changed>Empezar el capítulo de nuevo</button>
    <a class="button secondary" href="#/">← Volver</a>
  </main>`;
}

export function errorPage(bar: string, passage: string, message: string): string {
  return `<div class="reader">${bar}<tw-story><tw-passage>
    <div class="story-error"><b>Error en el pasaje «${esc(passage)}»</b><br>${esc(message)}</div>
  </tw-passage></tw-story></div>`;
}

/** "Tu camino": the ending reached, how many there are (unfound ones hidden), the choices made, how much was seen. */
function yourPath(discoveries: ChapterDiscoveries, found: Found, progress: Progress): string {
  const sum = summarize(discoveries, found);
  const current = discoveries.kind === "codes" ? progress.code : progress.passage;
  const chips = sum.endings
    .map((e) => `<span class="ending${e ? " found" : ""}${e && e === current ? " current" : ""}">${e ? esc(e) : "???"}</span>`)
    .join("");
  const choices = choicesOf(progress);
  const list = choices.length
    ? `<details class="path-choices"><summary>Tus decisiones (${choices.length})</summary><ol>${choices.map((c) => `<li>${esc(c)}</li>`).join("")}</ol></details>`
    : "";
  return `<section class="your-path">
    <h3>Tu camino</h3>
    <p>Finales descubiertos: <b>${sum.endingsFound}</b> de <b>${sum.endings.length}</b></p>
    <div class="endings">${chips}</div>
    ${list}
    <p class="path-explored">Has explorado ${sum.passagesSeen} de ${sum.passagesTotal} rincones de este capítulo.${
      sum.passagesSeen < sum.passagesTotal ? " Aún queda algo por descubrir: prueba otras decisiones, o el mismo camino en otro orden." : ""
    }</p>
  </section>`;
}

export interface EndState {
  series: SeriesEntry;
  nextChapter?: string;
  progress: Progress;
  discoveries: ChapterDiscoveries | null;
  found: Found;
}

export function endPanel(e: EndState): string {
  const code = e.progress.code ? `<p>Tu código: <b>${esc(e.progress.code)}</b>. Se guardará para el siguiente capítulo.</p>` : "";
  const next = e.nextChapter ? `<a class="button" href="#/${e.series.id}/${e.nextChapter}">Siguiente capítulo →</a>` : "";
  return `<footer class="end-panel">${code}${e.discoveries ? yourPath(e.discoveries, e.found, e.progress) : ""}
    <div class="end-actions"><a class="button secondary" href="#/capitulos/${e.series.id}">Índice</a><a class="button secondary" href="#/logros/${e.series.id}">Logros</a>${next}</div></footer>`;
}

export function unwrittenPanel(): string {
  return `<footer class="end-panel"><p>Este camino todavía no está escrito.</p>
    <div class="end-actions"><button class="button secondary" data-tool="undo">↶ Volver atrás</button></div></footer>`;
}

export function paceHint(): string {
  return `<div class="pace-hint" role="status">
    <button class="pace-next" data-pace="next">▼ Toca para continuar</button>
    <button class="pace-all" data-pace="all">Mostrar todo</button></div>`;
}
