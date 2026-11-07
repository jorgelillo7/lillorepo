/**
 * The chapter reader: holds the session, shows one passage at a time and
 * reacts to the reader. What the page looks like is in `views.ts`; how
 * progress moves is in `progression.ts`.
 */

import type { ChapterSummary, SeriesEntry } from "../contract.ts";
import type { ChapterDiscoveries } from "../engine/discoveries.ts";
import { ambienceFor, conditionFor, documentFor, inventoryOf, isSting, type ConditionState } from "../engine/game.ts";
import { Runtime, type Action, type Rendered, type Vars } from "../engine/runtime.ts";
import { hotspotsFor, type SceneFile } from "../engine/scenes.ts";
import { applyVolume, door as doorSound, heartbeat, setAmbience, step, sting } from "./audio.ts";
import { app, el, reducedMotion, setStoryCss, shortTitle } from "./dom.ts";
import { playDoor } from "./door.ts";
import { openStatus } from "./hud.ts";
import { library, loadChapter } from "./library.ts";
import { pace, type Pacing } from "./pacing.ts";
import { advance, finish, freshStart, outcomeOf, undo, withCarriedCode, withNewVariables, type Progress } from "./progression.ts";
import { clear, load, loadCodes, loadFound, loadMode, recordFound, store, storeCode, storeLastPlayed, storeMode } from "./save.ts";
import { settings, updateSettings } from "./settings.ts";
import { openSettings } from "./settings-ui.ts";
import * as view from "./views.ts";

interface Session {
  series: SeriesEntry;
  chapter: ChapterSummary;
  rt: Runtime;
  scenes: SceneFile | null;
  discoveries: ChapterDiscoveries | null;
  progress: Progress;
  /** The live state of the passage on screen (after it rendered, plus inputs and reveals). */
  vars: Vars;
  /** Every action on screen, including those revealed by a (link:). */
  actions: Action[];
  /** Scene shown last, so a change of room can play the door. */
  lastScene?: string;
  /** Set on a move, so arrival effects (pacing, steps, stings) never fire on undo or resume. */
  arrived: boolean;
}

let session: Session | null = null;
/** The reveal of the passage on screen, while it is still being read. */
let pacing: Pacing | null = null;

const HEART_BPM: Record<ConditionState["level"], number | null> = { fine: null, caution: null, danger: 84, critical: 112 };

export function closeChapter(): void {
  session = null;
  pacing = null;
  heartbeat(null);
}

export async function openChapter(seriesId: string, chapterId: string): Promise<void> {
  const series = library.find((s) => s.id === seriesId);
  const chapter = series?.chapters.find((c) => c.id === chapterId);
  if (!series || !chapter) {
    location.hash = "#/";
    return;
  }
  let data;
  try {
    data = await loadChapter(series.id, chapter.id);
  } catch {
    app.replaceChildren(
      el(`<main class="library"><p class="note">No se pudo cargar el capítulo. Revisa la conexión y vuelve a intentarlo.</p>
        <a class="button secondary" href="#/">← Volver</a></main>`),
    );
    return;
  }
  const rt = new Runtime(data);
  const hideHud = series.game.condition?.hideAuthorHud;
  setStoryCss(rt.story.stylesheet + (hideHud ? `\n${hideHud}{display:none !important}` : ""));
  document.title = shortTitle(rt.story.title);
  const saved = load(series.id, chapter.id);
  session = {
    series,
    chapter,
    rt,
    scenes: data.scenes,
    discoveries: data.discoveries,
    progress: saved ? withNewVariables(saved, rt.start()) : freshStart(rt.story.start, rt.start()),
    vars: {},
    actions: [],
    arrived: !saved,
  };
  storeLastPlayed(series.id, chapter.id);
  show();
}

function previousCode(s: Session): string | undefined {
  const i = s.series.chapters.indexOf(s.chapter);
  return i > 0 ? loadCodes(s.series.id)[s.series.chapters[i - 1].id] : undefined;
}

/** Render the saved passage from the saved state, record what was reached, and save. */
function show(): void {
  const s = session!;
  s.progress = withCarriedCode(s.progress, s.series.carry, previousCode(s));
  s.vars = structuredClone(s.progress.vars);
  let page: Rendered;
  try {
    page = s.rt.visit(s.vars, s.progress.passage);
  } catch (e) {
    app.replaceChildren(el(view.errorPage(toolbar(s), s.progress.passage, (e as Error).message)));
    return;
  }
  s.actions = [...page.actions];
  const outcome = outcomeOf(page, s.vars, s.series.carry);
  s.progress = finish(s.progress, outcome);
  if (outcome.ended && s.progress.code) storeCode(s.series.id, s.chapter.id, s.progress.code);
  recordFound(s.series.id, s.chapter.id, { passage: page.passage });
  if (outcome.ended) {
    const ending = s.discoveries?.kind === "codes" ? s.progress.code : page.passage;
    if (ending) recordFound(s.series.id, s.chapter.id, { ending });
  }
  store(s.series.id, s.chapter.id, s.progress);
  const footer = outcome.ended ? endPanel(s) : outcome.stuck ? view.unwrittenPanel() : "";
  renderPage(s, page, footer);
  if (s.arrived && isSting(s.series.game, s.chapter.id, page.passage)) sting();
  s.arrived = false;
}

function condition(s: Session): ConditionState | undefined {
  const cfg = s.series.game.condition;
  return cfg ? conditionFor(s.series.game, s.vars[cfg.variable]) : undefined;
}

function gameMode(s: Session): boolean {
  return Boolean(s.scenes) && loadMode() !== "text";
}

function toolbar(s: Session): string {
  return view.toolbar({
    series: s.series,
    title: s.rt.story.title,
    canUndo: s.progress.undo.length > 0,
    gameMode: s.scenes ? gameMode(s) : undefined,
    muted: settings().muted,
    condition: condition(s),
    items: inventoryOf(s.series.game, s.vars),
  });
}

function endPanel(s: Session): string {
  const i = s.series.chapters.indexOf(s.chapter);
  return view.endPanel({
    series: s.series,
    nextChapter: s.series.chapters[i + 1]?.id,
    progress: s.progress,
    discoveries: s.discoveries,
    found: loadFound(s.series.id)[s.chapter.id] ?? { endings: [], passages: [] },
  });
}

function renderPage(s: Session, page: Rendered, footer: string): void {
  const bar = toolbar(s);
  const passage = view.passageHtml(page.tags, page.html);
  const doc = documentFor(s.series.game, s.chapter.id, page.passage);
  if (doc) {
    // A document is read on its own sheet, whole; its page links still work.
    setAmbience(ambienceFor(s.series.game, undefined, page.tags));
    mount(s, view.documentPage(bar, doc.title, passage, footer));
    return;
  }
  const sceneId = gameMode(s) ? s.scenes?.passages[page.passage] : undefined;
  const scene = sceneId ? s.scenes!.scenes[sceneId] : undefined;
  setAmbience(ambienceFor(s.series.game, scene?.room, page.tags));
  if (!scene) {
    mount(s, view.textPage(bar, passage, footer));
    startPacing(s);
    if (s.arrived) step();
    return;
  }
  const lastRoom = s.lastScene ? s.scenes!.scenes[s.lastScene]?.room : undefined;
  const changedRoom = Boolean(lastRoom && scene.room && lastRoom !== scene.room);
  s.lastScene = sceneId;
  const { shown } = hotspotsFor(scene, page.actions, s.scenes!.scenes);
  const seen = new Set(s.progress.undo.map((u) => u.passage));
  const root = mount(s, view.scenePage(bar, scene, shown, page.actions, seen, passage, footer));
  // A link the scene already shows as a hotspot is not repeated in the text, unless the reader asked for both.
  const inScene = new Set(settings().sceneChoices === "both" ? [] : shown.flatMap((x) => x.actions.map(String)));
  root.querySelectorAll<HTMLElement>("tw-passage tw-link[data-action]").forEach((link) => {
    if (!inScene.has(link.dataset.action!)) return;
    if (link.nextElementSibling?.tagName === "BR") link.nextElementSibling.remove();
    link.remove();
  });
  startPacing(s);
  if (changedRoom) {
    playDoor();
    doorSound();
  } else if (s.arrived) step();
}

/** Put a page on screen with the condition's effects, scrolled to the top. */
function mount(s: Session, html: string): HTMLElement {
  const root = el(html);
  app.replaceChildren(root);
  const state = condition(s);
  const effects = settings().effects && !reducedMotion();
  root.dataset.condition = effects && state ? state.level : "fine";
  heartbeat(state ? HEART_BPM[state.level] : null);
  trackToolbarHeight(root.querySelector<HTMLElement>(".toolbar"));
  window.scrollTo({ top: 0 });
  return root;
}

let toolbarObserver: ResizeObserver | null = null;

/** Keep `--bar-h` at the toolbar's height, so the sticky scene sits right under it however the toolbar wraps. */
function trackToolbarHeight(bar: HTMLElement | null): void {
  toolbarObserver?.disconnect();
  if (!bar) return;
  const set = () => document.documentElement.style.setProperty("--bar-h", `${bar.offsetHeight}px`);
  set();
  toolbarObserver = new ResizeObserver(set);
  toolbarObserver.observe(bar);
}

/**
 * Reveal the passage paragraph by paragraph on arrival; everything at once on
 * undo, resume, or when the reader chose so. Hotspots and the end panel wait
 * until the text has been read.
 */
function startPacing(s: Session): void {
  const reader = app.querySelector<HTMLElement>(".reader")!;
  const passageEl = reader.querySelector<HTMLElement>("tw-passage");
  if (!passageEl) return;
  const instant = !s.arrived || settings().pacing === "all";
  reader.classList.add("pacing");
  const hint = el(view.paceHint());
  (reader.querySelector(".panel") ?? reader).appendChild(hint);
  pacing = pace(passageEl, instant, () => {
    reader.classList.remove("pacing");
    hint.remove();
    pacing = null;
  });
}

function navigate(s: Session, target: string, choice?: string): void {
  s.progress = advance(s.progress, target, s.vars, choice);
  s.arrived = true;
  show();
}

function onAction(s: Session, link: HTMLElement): void {
  const action = s.actions[Number(link.dataset.action)];
  if (!action) return;
  if (action.kind === "link") {
    navigate(s, action.target, action.label);
    return;
  }
  let out;
  try {
    out = s.rt.reveal(s.vars, action);
  } catch (e) {
    app.replaceChildren(el(view.errorPage(toolbar(s), s.progress.passage, (e as Error).message)));
    return;
  }
  if (out.goto) {
    navigate(s, out.goto, action.label);
    return;
  }
  // The revealed hook's actions join the page's, renumbered after them.
  const offset = s.actions.length;
  s.actions.push(...out.actions);
  const holder = document.createElement("tw-expansion");
  holder.innerHTML = out.html;
  holder.querySelectorAll<HTMLElement>("[data-action]").forEach((a) => {
    a.dataset.action = String(offset + Number(a.dataset.action));
  });
  link.replaceWith(holder);
}

/** Asks for a second tap within 4 s before a destructive action: embedded viewers block window.confirm(). */
function armed(tool: HTMLElement, question: string, label: string): boolean {
  if (tool.dataset.armed) return true;
  tool.dataset.armed = "1";
  tool.textContent = question;
  tool.classList.add("armed");
  setTimeout(() => {
    if (!tool.isConnected) return;
    delete tool.dataset.armed;
    tool.textContent = label;
    tool.classList.remove("armed");
  }, 4000);
  return false;
}

const TOOLS: Record<string, (s: Session, tool: HTMLElement) => void> = {
  settings: () => openSettings(() => show()),
  status: (s) => openStatus(s.series.game, condition(s), inventoryOf(s.series.game, s.vars)),
  mute: (_, tool) => {
    updateSettings({ muted: !settings().muted });
    applyVolume();
    tool.textContent = settings().muted ? "🔇" : "🔊";
  },
  mode: (s) => {
    storeMode(gameMode(s) ? "text" : "game");
    show();
  },
  undo: (s) => {
    const back = undo(s.progress);
    if (!back) return;
    s.progress = back;
    show();
  },
  restart: (s, tool) => {
    if (!armed(tool, "¿Seguro? Toca otra vez", "⟲ Reiniciar")) return;
    clear(s.series.id, s.chapter.id);
    s.progress = freshStart(s.rt.story.start, s.rt.start());
    s.lastScene = undefined;
    s.arrived = true;
    show();
  },
};

app.addEventListener("click", (ev) => {
  const target = ev.target as HTMLElement;
  const s = session;
  if (!s) return;
  const paceButton = target.closest<HTMLElement>("[data-pace]");
  if (paceButton && pacing) {
    if (paceButton.dataset.pace === "all") pacing.all();
    else pacing.next();
    return;
  }
  // While a passage is being read, a tap on its text or its scene shows the next paragraph.
  if (pacing && target.closest("tw-story, .stage") && !target.closest("tw-link, input, button, a")) {
    pacing.next();
    return;
  }
  const viewButton = target.closest<HTMLElement>(".hotspot[data-view]");
  if (viewButton) {
    showView(s, viewButton.dataset.view!);
    return;
  }
  const menuButton = target.closest<HTMLElement>(".hotspot[data-menu]");
  if (menuButton) {
    toggleMenu(menuButton);
    return;
  }
  const link = target.closest<HTMLElement>("tw-link[data-action], .hotspot[data-action], .hotspot-option[data-action]");
  if (link) {
    closeMenus();
    onAction(s, link);
    return;
  }
  if (!target.closest(".hotspot-menu")) closeMenus();
  const tool = target.closest<HTMLElement>("[data-tool]");
  if (tool) TOOLS[tool.dataset.tool!]?.(s, tool);
});

/**
 * Show another scene for the passage on screen — out through a door — with the
 * passage's choices on what they lead to. Only the picture changes: the text
 * stays as it is, read.
 */
function showView(s: Session, sceneId: string): void {
  const scene = s.scenes?.scenes[sceneId];
  const holder = app.querySelector<HTMLElement>(".stage-wrap");
  if (!scene || !holder) return;
  closeMenus();
  const lastRoom = s.lastScene ? s.scenes!.scenes[s.lastScene]?.room : undefined;
  s.lastScene = sceneId;
  const { shown } = hotspotsFor(scene, s.actions, s.scenes!.scenes);
  const seen = new Set(s.progress.undo.map((u) => u.passage));
  holder.innerHTML = view.stage(scene, shown, s.actions, seen);
  setAmbience(ambienceFor(s.series.game, scene.room, []));
  if (lastRoom && scene.room && lastRoom !== scene.room) {
    playDoor();
    doorSound();
  }
}

/** Open a hotspot's menu of the ways through it, closing any other. */
function toggleMenu(button: HTMLElement): void {
  const menu = app.querySelector<HTMLElement>(`.hotspot-menu[data-menu-of="${button.dataset.menu}"]`);
  if (!menu) return;
  const open = menu.hidden;
  closeMenus();
  menu.hidden = !open;
  button.setAttribute("aria-expanded", String(open));
  if (!open) return;
  placeMenu(menu, button);
  menu.querySelector<HTMLElement>(".hotspot-option")?.focus();
}

/** Below the object if the menu fits, else above it, else centred: always inside the picture, which may be small on a phone. */
function placeMenu(menu: HTMLElement, button: HTMLElement): void {
  const stage = menu.parentElement!.getBoundingClientRect();
  const spot = button.getBoundingClientRect();
  menu.style.maxHeight = `${stage.height - 8}px`;
  const { width, height } = menu.getBoundingClientRect();
  let top = spot.bottom - stage.top + 4;
  if (top + height > stage.height) top = spot.top - stage.top - height - 4;
  if (top < 0) top = (stage.height - height) / 2;
  const left = Math.min(Math.max(0, spot.left - stage.left), stage.width - width);
  menu.style.top = `${Math.max(4, top)}px`;
  menu.style.left = `${Math.max(0, left)}px`;
}

function closeMenus(): void {
  app.querySelectorAll<HTMLElement>(".hotspot-menu").forEach((m) => (m.hidden = true));
  app.querySelectorAll<HTMLElement>(".hotspot[data-menu]").forEach((b) => b.setAttribute("aria-expanded", "false"));
}

// On the window: with nothing focused, keys go to the body, outside the app.
window.addEventListener("keydown", (ev) => {
  const t = ev.target as HTMLElement;
  if (ev.key === "Escape") closeMenus();
  if (pacing && (ev.key === " " || ev.key === "Enter") && !t.closest?.("tw-link, input, button, a")) {
    ev.preventDefault();
    pacing.next();
  }
});

app.addEventListener("keydown", (ev) => {
  const link = (ev.target as HTMLElement).closest?.<HTMLElement>("tw-link[data-action]");
  if (session && link && (ev.key === "Enter" || ev.key === " ")) {
    ev.preventDefault();
    onAction(session, link);
  }
});

app.addEventListener("input", (ev) => {
  const input = ev.target as HTMLInputElement;
  if (session && input.dataset.bind) session.vars[input.dataset.bind] = input.value;
});
