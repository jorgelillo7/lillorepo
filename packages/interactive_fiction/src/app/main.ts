/** The reader app: a library of series, each a list of chapters, and the chapter reader. */

import "./harlowe.css";
import "./app.css";
import { Runtime, type Action, type Rendered, type Vars } from "../engine/runtime.ts";
import { hotspotsFor, type SceneFile } from "../engine/scenes.ts";
import type { Story } from "../engine/source.ts";
import { toText } from "../engine/values.ts";
import { clear, load, loadCodes, loadMode, store, storeCode, storeMode, type Progress } from "./save.ts";

type Chapter = Story & { scenes: SceneFile | null };

interface ChapterInfo {
  id: string;
  title: string;
  draft: boolean;
}

interface SeriesInfo {
  id: string;
  title: string;
  carry: { from: string; to: string } | null;
  about: string[];
  chapters: ChapterInfo[];
}

const app = document.getElementById("app")!;
let library: SeriesInfo[] = [];
const stories = new Map<string, Chapter>();

function el(html: string): HTMLElement {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild as HTMLElement;
}

function esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

/** Chapter titles come as "Capitulo 2 - ¿Qué es este lugar?"; the list shows the part after the dash. */
function shortTitle(title: string): string {
  const m = /^\s*cap[ií]tulo\s+\d+\s*[-–—:]\s*(.+)$/i.exec(title);
  return m ? m[1].trim() : title;
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path);
  if (!res.ok) throw new Error(`${path}: ${res.status}`);
  return (await res.json()) as T;
}

async function story(series: string, chapter: string): Promise<Chapter> {
  const k = `${series}/${chapter}`;
  let s = stories.get(k);
  if (!s) {
    s = await fetchJson<Chapter>(`stories/${k}.json`);
    stories.set(k, s);
  }
  return s;
}

function setStoryCss(css: string): void {
  let tag = document.getElementById("story-css");
  if (!tag) {
    tag = document.createElement("style");
    tag.id = "story-css";
    document.head.appendChild(tag);
  }
  tag.textContent = css;
}

// --- library --------------------------------------------------------------

function status(series: SeriesInfo, chapter: ChapterInfo): string {
  const p = load(series.id, chapter.id);
  const code = loadCodes(series.id)[chapter.id];
  const earned = code ? ` · código <b>${esc(code)}</b>` : "";
  if (!p) return "Sin empezar";
  return (p.finished ? "Terminado" : "En curso") + earned;
}

function renderLibrary(): void {
  setStoryCss("");
  document.title = library.length === 1 ? library[0].title : "Historias";
  const blocks = library.map((series) => {
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
    el(`<main class="library">${blocks.join("")}<p class="note">Tu progreso se guarda en este navegador.</p></main>`),
  );
}

function renderAbout(seriesId: string): void {
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

// --- reader ---------------------------------------------------------------

interface Session {
  series: SeriesInfo;
  chapter: ChapterInfo;
  rt: Runtime;
  scenes: SceneFile | null;
  /** Scene shown last, so a change of room can play the door. */
  lastScene?: string;
  vars: Vars;
  progress: Progress;
  actions: Action[];
}

let session: Session | null = null;

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

async function openChapter(seriesId: string, chapterId: string): Promise<void> {
  const series = library.find((s) => s.id === seriesId);
  const chapter = series?.chapters.find((c) => c.id === chapterId);
  if (!series || !chapter) {
    location.hash = "#/";
    return;
  }
  const data = await story(series.id, chapter.id);
  const rt = new Runtime(data);
  setStoryCss(rt.story.stylesheet);
  document.title = shortTitle(rt.story.title);
  const progress = load(series.id, chapter.id) ?? freshStart(rt);
  session = { series, chapter, rt, scenes: data.scenes, vars: {}, progress, actions: [] };
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
    <a class="tool" href="#/">← Capítulos</a>
    <span class="tool-title">${esc(shortTitle(s.rt.story.title))}</span>
    ${mode}
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
  return `<footer class="end-panel">${code}<div class="end-actions"><a class="button secondary" href="#/">Índice</a>${nextLink}</div></footer>`;
}

function unwrittenPanel(): string {
  return `<footer class="end-panel"><p>Este camino todavía no está escrito.</p>
    <div class="end-actions"><button class="button secondary" data-tool="undo">↶ Volver atrás</button></div></footer>`;
}

function renderPage(page: Rendered, footer: string): void {
  const tags = esc(page.tags.join(" "));
  const passage = `<tw-story tags="${tags}"><tw-passage tags="${tags}">${page.html}</tw-passage></tw-story>`;
  const s = session!;
  const sceneId = gameMode() ? s.scenes?.passages[page.passage] : undefined;
  const scene = sceneId ? s.scenes!.scenes[sceneId] : undefined;
  if (!scene) {
    app.replaceChildren(el(`<div class="reader">${toolbar()}${passage}${footer}</div>`));
    window.scrollTo({ top: 0 });
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
  window.scrollTo({ top: 0 });
  if (changedRoom) playDoor();
}

/** The survival-horror door between rooms. Click to skip; off when the reader asks for less motion. */
function playDoor(): void {
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const door = el(`<div class="door-transition" aria-hidden="true">
    <div class="door-frame"><div class="door-leaf"><span class="door-knob"></span></div></div></div>`);
  const done = () => door.remove();
  door.addEventListener("click", done);
  door.addEventListener("animationend", (e) => {
    if ((e as AnimationEvent).animationName === "door-fade") done();
  });
  document.body.appendChild(door);
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
  const link = target.closest<HTMLElement>("tw-link[data-action], .hotspot[data-action]");
  if (link && session) {
    onAction(link);
    return;
  }
  const tool = target.closest<HTMLElement>("[data-tool]");
  if (!tool || !session) return;
  const s = session;
  if (tool.dataset.tool === "mode") {
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
    show();
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

// --- routing --------------------------------------------------------------

function route(): void {
  const [, seriesId, chapterId] = location.hash.replace(/^#\/?/, "#/").split("/");
  if (seriesId === "acerca" && chapterId) {
    session = null;
    renderAbout(chapterId);
  } else if (seriesId && chapterId) void openChapter(seriesId, chapterId);
  else {
    session = null;
    renderLibrary();
  }
}

async function boot(): Promise<void> {
  try {
    library = await fetchJson<SeriesInfo[]>("stories/library.json");
  } catch {
    app.replaceChildren(el(`<main class="library"><p class="note">No hay historias publicadas.</p></main>`));
    return;
  }
  window.addEventListener("hashchange", route);
  route();
}

void boot();
