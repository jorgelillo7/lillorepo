/** The chapter reader: one passage at a time, its actions, undo, restart, game and text modes. */

import { ambienceFor, conditionFor, documentFor, inventoryOf, isSting, type ConditionState } from "../engine/game.ts";
import { Runtime, type Action, type Rendered, type Vars } from "../engine/runtime.ts";
import { hotspotsFor, type SceneFile } from "../engine/scenes.ts";
import { toText } from "../engine/values.ts";
import { app, el, esc, reducedMotion, setStoryCss, shortTitle } from "./dom.ts";
import { door as doorSound, heartbeat, setAmbience, step, sting, applyVolume } from "./audio.ts";
import { playDoor } from "./door.ts";
import { openStatus, statusButton } from "./hud.ts";
import { openSettings } from "./settings-ui.ts";
import { pace, type Pacing } from "./pacing.ts";
import { settings, updateSettings } from "./settings.ts";
import { library, loadChapter, type ChapterInfo, type SeriesInfo } from "./library.ts";
import { clear, load, loadCodes, loadMode, store, storeCode, storeLastPlayed, storeMode, type Progress } from "./save.ts";

interface Session {
  series: SeriesInfo;
  chapter: ChapterInfo;
  rt: Runtime;
  scenes: SceneFile | null;
  /** Scene shown last, so a change of room can play the door. */
  lastScene?: string;
  /** Set by a click, so a sting plays on arrival and never on undo or resume. */
  arrived?: boolean;
  vars: Vars;
  progress: Progress;
  actions: Action[];
}

export let session: Session | null = null;
/** The reveal of the passage on screen, while it is still being read. */
let pacing: Pacing | null = null;

export function closeChapter(): void {
  session = null;
  heartbeat(null);
}

function freshStart(rt: Runtime): Progress {
  return { passage: rt.story.start, vars: rt.start(), undo: [], finished: false };
}

/** The code the previous chapter ended with, written into this chapter's code field while it is empty. */
function carryCode(s: Session): void {
  const carry = s.series.carry;
  const i = s.series.chapters.indexOf(s.chapter);
  if (!carry || i <= 0 || s.progress.vars[carry.to] !== "") return;
  const code = loadCodes(s.series.id)[s.series.chapters[i - 1].id];
  if (code) s.progress.vars[carry.to] = code;
}

export async function openChapter(seriesId: string, chapterId: string): Promise<void> {
  const series = library.find((s) => s.id === seriesId);
  const chapter = series?.chapters.find((c) => c.id === chapterId);
  if (!series || !chapter) {
    location.hash = "#/";
    return;
  }
  const data = await loadChapter(series.id, chapter.id);
  const rt = new Runtime(data);
  const hideHud = series.game.condition?.hideAuthorHud;
  setStoryCss(rt.story.stylesheet + (hideHud ? `\n${hideHud}{display:none !important}` : ""));
  document.title = shortTitle(rt.story.title);
  const saved = load(series.id, chapter.id);
  const progress = saved ?? freshStart(rt);
  session = { series, chapter, rt, scenes: data.scenes, vars: {}, progress, actions: [], arrived: !saved };
  storeLastPlayed(series.id, chapter.id);
  show();
}

/** Render the saved passage from the saved state. */
function show(): void {
  const s = session!;
  carryCode(s);
  s.vars = structuredClone(s.progress.vars);
  let page: Rendered;
  try {
    page = s.rt.visit(s.vars, s.progress.passage);
  } catch (e) {
    renderError(e as Error);
    return;
  }
  s.actions = [...page.actions];
  const stuck = page.actions.length === 0 && page.inputs.length === 0;
  // A chapter that keeps an end code has ended only once the code is set;
  // a link-less passage before that is a path not written yet (drafts).
  const carry = s.series.carry;
  const code = carry ? s.vars[carry.from] : undefined;
  const ended = stuck && (code === undefined || toText(code) !== "");
  if (ended && !s.progress.finished) {
    s.progress.finished = true;
    s.progress.code = code !== undefined ? toText(code) : undefined;
    if (s.progress.code) storeCode(s.series.id, s.chapter.id, s.progress.code);
  }
  store(s.series.id, s.chapter.id, s.progress);
  renderPage(page, ended ? endPanel() : stuck ? unwrittenPanel() : "");
  if (s.arrived && isSting(s.series.game, s.chapter.id, page.passage)) sting();
  s.arrived = false;
}

function condition(): ConditionState | undefined {
  const s = session!;
  const cfg = s.series.game.condition;
  return cfg ? conditionFor(s.series.game, s.vars[cfg.variable]) : undefined;
}

const HEART_BPM: Record<ConditionState["level"], number | null> = { fine: null, caution: null, danger: 84, critical: 112 };

/** The condition's effects on the page and the heartbeat; off with reduced motion or the setting. */
function applyCondition(root: HTMLElement): void {
  const state = condition();
  const effects = settings().effects && !reducedMotion();
  root.dataset.condition = effects && state ? state.level : "fine";
  heartbeat(state ? HEART_BPM[state.level] : null);
}

function gameMode(): boolean {
  return Boolean(session?.scenes) && loadMode() !== "text";
}

function toolbar(): string {
  const s = session!;
  const canUndo = s.progress.undo.length > 0;
  const mode = s.scenes
    ? `<button class="tool" data-tool="mode">${gameMode() ? "📖 Texto" : "🎮 Juego"}</button>`
    : "";
  return `<nav class="toolbar">
    <a class="tool" href="#/capitulos/${s.series.id}">← Capítulos</a>
    <span class="tool-title">${esc(shortTitle(s.rt.story.title))}</span>
    ${statusButton(condition(), inventoryOf(s.series.game, s.vars))}
    ${mode}
    <button class="tool" data-tool="mute" aria-label="Sonido">${settings().muted ? "🔇" : "🔊"}</button>
    <button class="tool" data-tool="settings" aria-label="Ajustes">⚙</button>
    <button class="tool" data-tool="undo" ${canUndo ? "" : "disabled"}>↶ Atrás</button>
    <button class="tool" data-tool="restart">⟲ Reiniciar</button>
  </nav>`;
}

function endPanel(): string {
  const s = session!;
  const i = s.series.chapters.indexOf(s.chapter);
  const next = s.series.chapters[i + 1];
  const code = s.progress.code ? `<p>Tu código: <b>${esc(s.progress.code)}</b>. Se guardará para el siguiente capítulo.</p>` : "";
  const nextLink = next ? `<a class="button" href="#/${s.series.id}/${next.id}">Siguiente capítulo →</a>` : "";
  return `<footer class="end-panel">${code}<div class="end-actions"><a class="button secondary" href="#/capitulos/${s.series.id}">Índice</a>${nextLink}</div></footer>`;
}

function unwrittenPanel(): string {
  return `<footer class="end-panel"><p>Este camino todavía no está escrito.</p>
    <div class="end-actions"><button class="button secondary" data-tool="undo">↶ Volver atrás</button></div></footer>`;
}

function renderPage(page: Rendered, footer: string): void {
  const tags = esc(page.tags.join(" "));
  const passage = `<tw-story tags="${tags}"><tw-passage tags="${tags}">${page.html}</tw-passage></tw-story>`;
  const s = session!;
  const doc = documentFor(s.series.game, s.chapter.id, page.passage);
  if (doc) {
    // A document is read on its own sheet; its page links still work.
    setAmbience(ambienceFor(s.series.game, undefined, page.tags));
    const root = el(`<div class="reader doc-reader">${toolbar()}
      <div class="doc-overlay"><div class="doc-sheet"><h2 class="doc-title">${esc(doc.title)}</h2>${passage}${footer}</div></div></div>`);
    app.replaceChildren(root);
    applyCondition(root);
    window.scrollTo({ top: 0 });
    return;
  }
  const sceneId = gameMode() ? s.scenes?.passages[page.passage] : undefined;
  const scene = sceneId ? s.scenes!.scenes[sceneId] : undefined;
  setAmbience(ambienceFor(s.series.game, scene?.room, page.tags));
  if (!scene) {
    const root = el(`<div class="reader">${toolbar()}${passage}${footer}</div>`);
    app.replaceChildren(root);
    applyCondition(root);
    window.scrollTo({ top: 0 });
    startPacing();
    if (s.arrived) step();
    return;
  }
  const lastRoom = s.lastScene ? s.scenes!.scenes[s.lastScene]?.room : undefined;
  const changedRoom = Boolean(lastRoom && scene.room && lastRoom !== scene.room);
  s.lastScene = sceneId;
  const { shown } = hotspotsFor(scene, page.actions);
  const seen = new Set(s.progress.undo.map((u) => u.passage));
  const spots = shown
    .map(({ hotspot, action }) => {
      const [x, y, w, h] = hotspot.rect;
      const target = (page.actions[action] as { target: string }).target;
      const visited = seen.has(target) ? " visited" : "";
      return `<button class="hotspot${visited}" data-action="${action}" aria-label="${esc(hotspot.label)}"
        style="left:${x}%;top:${y}%;width:${w}%;height:${h}%"><span class="hotspot-label">${esc(hotspot.label)}</span></button>`;
    })
    .join("");
  const [aw, ah] = scene.aspect;
  const root = el(`<div class="reader game">${toolbar()}
    <div class="game-layout">
      <div class="stage-wrap"><div class="stage" style="--ar:${aw / ah}">
        <img src="${esc(scene.image)}" alt="" draggable="false">${spots}
      </div></div>
      <section class="panel">${passage}${footer}</section>
    </div></div>`);
  // A link the scene already shows as a hotspot is not repeated in the text.
  const inScene = new Set(shown.map((x) => String(x.action)));
  root.querySelectorAll<HTMLElement>("tw-passage tw-link[data-action]").forEach((link) => {
    if (!inScene.has(link.dataset.action!)) return;
    if (link.nextElementSibling?.tagName === "BR") link.nextElementSibling.remove();
    link.remove();
  });
  app.replaceChildren(root);
  applyCondition(root);
  window.scrollTo({ top: 0 });
  startPacing();
  if (changedRoom) {
    playDoor();
    doorSound();
  } else if (s.arrived) step();
}

/**
 * Reveal the passage paragraph by paragraph on arrival; everything at once on
 * undo, resume, or when the reader chose so. Hotspots and the end panel wait
 * until the text has been read.
 */
function startPacing(): void {
  const s = session!;
  const reader = app.querySelector<HTMLElement>(".reader")!;
  const passageEl = reader.querySelector<HTMLElement>("tw-passage");
  if (!passageEl) return;
  const instant = !s.arrived || settings().pacing === "all";
  reader.classList.add("pacing");
  const hint = el(`<div class="pace-hint" role="status">
    <button class="pace-next" data-pace="next">▼ Toca para continuar</button>
    <button class="pace-all" data-pace="all">Mostrar todo</button></div>`);
  (reader.querySelector(".panel") ?? reader).appendChild(hint);
  pacing = pace(passageEl, instant, () => {
    reader.classList.remove("pacing");
    hint.remove();
    pacing = null;
  });
}

function renderError(e: Error): void {
  const s = session!;
  app.replaceChildren(
    el(`<div class="reader">${toolbar()}<tw-story><tw-passage>
      <div class="story-error"><b>Error en el pasaje «${esc(s.progress.passage)}»</b><br>${esc(e.message)}</div>
    </tw-passage></tw-story></div>`),
  );
}

function navigate(target: string): void {
  const s = session!;
  s.progress.undo.push({ passage: s.progress.passage, vars: s.progress.vars });
  s.progress = { ...s.progress, passage: target, vars: structuredClone(s.vars), finished: false, code: undefined };
  s.arrived = true;
  show();
}

function onAction(link: HTMLElement): void {
  const s = session!;
  const action = s.actions[Number(link.dataset.action)];
  if (!action) return;
  if (action.kind === "link") {
    navigate(action.target);
    return;
  }
  let out;
  try {
    out = s.rt.reveal(s.vars, action);
  } catch (e) {
    renderError(e as Error);
    return;
  }
  if (out.goto) {
    navigate(out.goto);
    return;
  }
  const offset = s.actions.length;
  s.actions.push(...out.actions);
  const holder = document.createElement("tw-expansion");
  holder.innerHTML = out.html;
  holder.querySelectorAll<HTMLElement>("[data-action]").forEach((a) => {
    a.dataset.action = String(offset + Number(a.dataset.action));
  });
  link.replaceWith(holder);
}

app.addEventListener("click", (ev) => {
  const target = ev.target as HTMLElement;
  const paceButton = target.closest<HTMLElement>("[data-pace]");
  if (paceButton && pacing) {
    if (paceButton.dataset.pace === "all") pacing.all();
    else pacing.next();
    return;
  }
  // While a passage is being read, a tap on its text shows the next paragraph.
  if (pacing && target.closest("tw-story") && !target.closest("tw-link, input, button, a")) {
    pacing.next();
    return;
  }
  const link = target.closest<HTMLElement>("tw-link[data-action], .hotspot[data-action]");
  if (link && session) {
    onAction(link);
    return;
  }
  const tool = target.closest<HTMLElement>("[data-tool]");
  if (!tool || !session) return;
  const s = session;
  if (tool.dataset.tool === "settings") {
    openSettings(() => show());
  } else if (tool.dataset.tool === "status") {
    openStatus(s.series.game, condition(), inventoryOf(s.series.game, s.vars));
  } else if (tool.dataset.tool === "mute") {
    updateSettings({ muted: !settings().muted });
    applyVolume();
    tool.textContent = settings().muted ? "🔇" : "🔊";
  } else if (tool.dataset.tool === "mode") {
    storeMode(gameMode() ? "text" : "game");
    show();
  } else if (tool.dataset.tool === "undo") {
    const prev = s.progress.undo.pop();
    if (!prev) return;
    s.progress = { ...s.progress, ...prev, finished: false, code: undefined };
    show();
  } else if (tool.dataset.tool === "restart" && !tool.dataset.armed) {
    // Asked in the page: embedded viewers block window.confirm().
    tool.dataset.armed = "1";
    tool.textContent = "¿Seguro? Toca otra vez";
    tool.classList.add("armed");
    setTimeout(() => {
      if (!tool.isConnected) return;
      delete tool.dataset.armed;
      tool.textContent = "⟲ Reiniciar";
      tool.classList.remove("armed");
    }, 4000);
  } else if (tool.dataset.tool === "restart") {
    clear(s.series.id, s.chapter.id);
    s.progress = freshStart(s.rt);
    s.lastScene = undefined;
    s.arrived = true;
    show();
  }
});

// On the window: with nothing focused, keys go to the body, outside the app.
window.addEventListener("keydown", (ev) => {
  const t = ev.target as HTMLElement;
  if (pacing && (ev.key === " " || ev.key === "Enter") && !t.closest?.("tw-link, input, button, a")) {
    ev.preventDefault();
    pacing.next();
  }
});

app.addEventListener("keydown", (ev) => {
  const link = (ev.target as HTMLElement).closest?.<HTMLElement>("tw-link[data-action]");
  if (link && (ev.key === "Enter" || ev.key === " ")) {
    ev.preventDefault();
    onAction(link);
  }
});

app.addEventListener("input", (ev) => {
  const input = ev.target as HTMLInputElement;
  if (session && input.dataset.bind) session.vars[input.dataset.bind] = input.value;
});
