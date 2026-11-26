/**
 * 3D draft of a chapter: the reader's own engine runs the passages; a scene
 * with a generated world (worlds.json) is shown as a Gaussian-splat room whose
 * hotspots sit where the build cast them from the 2D scene file onto the
 * world's collider (bake.ts; the page downloads no mesh), and any other scene
 * falls back to its 2D picture. The passage reads as
 * subtitles, a paragraph at a time; touching something opens its choices and
 * moves the camera towards it.
 */

import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import * as THREE from "three";
import { applyVolume, door, heartbeat, setAmbience, step, sting, unlock } from "../../src/app/audio.ts";
import { segment } from "../../src/app/pacing.ts";
import { freshStart, isStale, outcomeOf, withCarriedCode, withNewVariables, type Outcome } from "../../src/app/progression.ts";
import { clear, lastPlayed, load, loadCodes, loadFound, recordFound, store, storeCode, storeLastPlayed } from "../../src/app/save.ts";
import { applySettings, settings, updateSettings, type Settings } from "../../src/app/settings.ts";
import { achievements, summarize } from "../../src/engine/discoveries.ts";
import type { ChapterData, ChapterSummary, SeriesEntry } from "../../src/contract.ts";
import { conditionFor, isSting, type Ambience, type ConditionState } from "../../src/engine/game.ts";
import { Runtime, type Action } from "../../src/engine/runtime.ts";
import { hotspotsFor, type Hotspot, type Scene, type SceneFile, type ShownHotspot } from "../../src/engine/scenes.ts";
import type { BakedRoom, Served, ServedWorld as World } from "./publish.ts";

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const stage = $<HTMLElement>("stage");
const canvas = $<HTMLCanvasElement>("world");
const flat = $<HTMLImageElement>("flat");
const spots = $<HTMLDivElement>("spots");
const subs = $<HTMLElement>("subs");
const subsText = $<HTMLElement>("subs-text");
const subsNext = $<HTMLButtonElement>("subs-next");
const subsClose = $<HTMLButtonElement>("subs-close");
const reopen = $<HTMLButtonElement>("reopen");
const prompt = $<HTMLElement>("prompt");

const [library, served] = await Promise.all([
  fetch("/library.json").then((r) => r.json() as Promise<SeriesEntry[]>),
  fetch("/worlds.json").then((r) => r.json() as Promise<Served>),
]);
const series = library[0];
const { worlds, rooms } = served;
/** World files are named by their content (prepare.ts) and cached for good: no stamp to add. */
const asset = (path: string) => `/${path}`;

interface Chapter {
  id: string;
  data: ChapterData;
  rt: Runtime;
  scenes: SceneFile;
}
const chapterData = new Map<string, Promise<Chapter>>();
/** A chapter's built data (prepare.ts copies every chapter of the series), fetched once. */
function loadChapter(id: string): Promise<Chapter> {
  let p = chapterData.get(id);
  if (!p) {
    p = fetch(`/${id}.json`).then(async (r) => {
      if (!r.ok) throw new Error(`No chapter ${id}`);
      const data = (await r.json()) as ChapterData;
      return { id, data, rt: new Runtime(data), scenes: data.scenes ?? { scenes: {}, passages: {} } };
    });
    chapterData.set(id, p);
  }
  return p;
}
let chapter = await loadChapter(series.chapters[0].id);
const shortName = (title: string) => title.replace(/^Cap[ií]tulo \d+\s*-\s*/i, "");

$("title-name").textContent = series.title;
$("title-warning").textContent = series.game.title?.warning ?? "";
// Opened from the home screen already: the tip has done its job.
// The tip is for iPhone and iPad only, and only until the game is opened from the home screen.
const apple = /iPhone|iPad/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
if (!apple || (navigator as Navigator & { standalone?: boolean }).standalone || matchMedia("(display-mode: fullscreen), (display-mode: standalone)").matches) {
  $("title-tip").hidden = true;
}
// The author's own components (a book page, the rules) keep his styling; rules that lay out his whole page do not apply here.
const authorCss = document.createElement("style");
document.head.append(authorCss);
const setAuthorCss = (c: Chapter) =>
  (authorCss.textContent = (c.data.stylesheet ?? "").replace(/[^{}]*(?:tw-story|tw-passage|\bbody\b|\bhtml\b)[^{}]*\{[^{}]*\}/g, ""));

// --- 3D -------------------------------------------------------------------

const renderer = new THREE.WebGLRenderer({ canvas, antialias: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene3d = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(46, 1, 0.01, 200);
scene3d.add(new SparkRenderer({ renderer }));
/** Marble worlds use OpenCV axes (y down, z forward); three.js has y up, z back. */
const OPENCV_TO_THREE = new THREE.Quaternion(1, 0, 0, 0);
const NO_ROOM: BakedRoom = { anchors: {}, figures: [] };

interface Loaded {
  id: string;
  /** The world's scene as the playing chapter has it: its hotspots, and so its anchors, differ between chapters. */
  scene: Scene;
  world: World;
  splat: SplatMesh;
  figures: THREE.Object3D[];
  anchors: Map<string, THREE.Vector3>;
}
/** A world's splats by file, shared by every chapter and every scene that shows its room. */
const assets = new Map<string, Promise<SplatMesh>>();
/** How much of each splat file has arrived, 0–1, for whoever is waiting on it; null while its size is unknown. */
const progress = new Map<string, number | null>();
const watchers = new Set<() => void>();
/** A world as one chapter shows it, by "chapter/scene"; `settled` holds those ready to show at once. */
const loaded = new Map<string, Promise<Loaded>>();
const settled = new Set<string>();
let current: Loaded | null = null;
/** Where the view is, easing towards where the reader has turned it (`aim`), which keeps a little of the drag's speed on release. */
let yaw = 0;
let pitch = 0;
const aim = { yaw: 0, pitch: 0, yawSpeed: 0, pitchSpeed: 0 };
const PITCH_RANGE = 0.35;
const calm = matchMedia("(prefers-reduced-motion: reduce)");

/** The splat file whose download the title's line and the fade's line show, if any. */
let awaited: string | null = null;
const loadingLine = $<HTMLElement>("title-loading");
const loadingBar = $<HTMLProgressElement>("title-loading-bar");
const loadingPercent = $<HTMLElement>("title-loading-percent");
function showProgress(): void {
  const done = awaited === null ? 1 : (progress.get(awaited) ?? null);
  loadingLine.hidden = awaited === null || done === 1;
  stage.classList.toggle("loading-unknown", done === null);
  if (done === null) {
    loadingBar.removeAttribute("value");
    loadingPercent.textContent = "";
    return;
  }
  stage.style.setProperty("--loaded", String(done));
  loadingBar.value = done;
  loadingPercent.textContent = `${Math.round(done * 100)} %`;
}
watchers.add(showProgress);
/** Show `world`'s download until `ready` settles. */
async function waitingOn<T>(world: World, ready: Promise<T>): Promise<T> {
  awaited = world.splats;
  showProgress();
  try {
    return await ready;
  } finally {
    if (awaited === world.splats) awaited = null;
    showProgress();
  }
}

function loadAssets(world: World): Promise<SplatMesh> {
  let p = assets.get(world.splats);
  if (!p) {
    progress.set(world.splats, null);
    p = (async () => {
      const splat = new SplatMesh({
        url: asset(world.splats),
        onProgress: (e) => {
          if (e.lengthComputable && e.total) progress.set(world.splats, e.loaded / e.total);
          watchers.forEach((w) => w());
        },
      });
      splat.quaternion.copy(OPENCV_TO_THREE);
      await splat.initialized;
      progress.set(world.splats, 1);
      watchers.forEach((w) => w());
      return splat;
    })();
    assets.set(world.splats, p);
  }
  return p;
}

/**
 * Keep in memory only the room on screen and the rooms one choice away:
 * download those ahead, free every other. A chapter's rooms all at once would
 * be ~85 MB to download and a dozen worlds in a phone's memory.
 */
async function keepAround(c: Chapter, sceneId: string | undefined, page: Action[]): Promise<void> {
  const near = new Set<string>();
  if (sceneId && worlds[sceneId]) near.add(sceneId);
  for (const a of page) {
    const s = a.kind === "link" ? c.scenes.passages[a.target] : undefined;
    if (s && worlds[s]) near.add(s);
  }
  const keepFiles = new Set([...near].map((s) => worlds[s].splats));
  if (current) keepFiles.add(current.world.splats);
  for (const [file, p] of assets) {
    if (keepFiles.has(file)) continue;
    assets.delete(file);
    for (const [key, l] of loaded) {
      if (worlds[key.split("/")[1]]?.splats !== file) continue;
      loaded.delete(key);
      settled.delete(key);
      void l.then((w) => w.figures.forEach(disposeFigure)).catch(() => undefined);
    }
    progress.delete(file);
    void p.then((splat) => splat.dispose()).catch(() => undefined);
  }
  for (const s of near) {
    if (c !== chapter) return;
    await loadWorld(c, s).catch(() => undefined);
  }
}

function disposeFigure(f: THREE.Object3D): void {
  const mesh = f as THREE.Mesh<THREE.BufferGeometry, THREE.MeshBasicMaterial>;
  mesh.geometry.dispose();
  mesh.material.map?.dispose();
  mesh.material.dispose();
}

function loadWorld(c: Chapter, id: string): Promise<Loaded> {
  const key = `${c.id}/${id}`;
  let p = loaded.get(key);
  if (!p) {
    const world = worlds[id];
    const scene = c.scenes.scenes[id];
    p = (async () => {
      const room = rooms[key] ?? NO_ROOM;
      const [splat, figures] = await Promise.all([loadAssets(world), Promise.all(room.figures.map(figure))]);
      settled.add(key);
      return { id, scene, world, splat, figures, anchors: new Map(Object.entries(room.anchors).map(([label, at]) => [label, new THREE.Vector3(...at)])) };
    })();
    loaded.set(key, p);
  }
  return p;
}

/** A cut-out laid into the room on the quad the build placed for it: sharp where a world bakes a person in soft. */
async function figure(f: BakedRoom["figures"][number]): Promise<THREE.Object3D> {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute(f.corners.flat(), 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute([0, 1, 1, 1, 0, 0, 1, 0], 2));
  geometry.setIndex([0, 2, 1, 1, 2, 3]);
  const texture = await new THREE.TextureLoader().loadAsync(asset(f.image));
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
  const mesh = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({ map: texture, transparent: true, depthTest: false, depthWrite: false, side: THREE.DoubleSide }));
  mesh.renderOrder = 10;
  return mesh;
}

/** Width over height of the trimmed picture the world was generated from. */
function pictureAspect(scene: Scene, world: World): number {
  const [w, h] = scene.aspect;
  return (w * (1 - 2 * world.crop[0])) / (h * (1 - 2 * world.crop[1]));
}

/**
 * The vertical field of view that keeps the picture's whole width in view on a
 * narrower stage (capped, so a phone in portrait looks around instead of warping).
 */
function fovFor(l: Loaded, aspect: number): number {
  // The picture's width is what the world knows: a wider screen trims top and bottom rather than show more sideways.
  const halfTan = Math.tan(THREE.MathUtils.degToRad(l.world.fovY / 2)) * pictureAspect(l.scene, l.world);
  return Math.min(90, THREE.MathUtils.radToDeg(2 * Math.atan(halfTan / aspect)));
}

/** The turn allowed now, in radians: the view's edges stay inside the world's bounds. */
function yawRange(l: Loaded): [number, number] {
  const half = THREE.MathUtils.radToDeg(Math.atan(Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)) * camera.aspect));
  const picture = THREE.MathUtils.radToDeg(Math.atan(Math.tan(THREE.MathUtils.degToRad(l.world.fovY / 2)) * pictureAspect(l.scene, l.world)));
  const [right, left] = l.world.bounds ?? [-(picture + 10), picture + 10];
  // A world clean all the way round turns freely.
  if (left - right >= 360) return [-Infinity, Infinity];
  const lo = right + half;
  const hi = left - half;
  const deg = lo <= hi ? [lo, hi] : [(lo + hi) / 2, (lo + hi) / 2];
  return [THREE.MathUtils.degToRad(deg[0]), THREE.MathUtils.degToRad(deg[1])];
}

function resize(): void {
  const { clientWidth: w, clientHeight: h } = stage;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.fov = current ? fovFor(current, camera.aspect) : 46;
  camera.updateProjectionMatrix();
  if (current) {
    const [lo, hi] = yawRange(current);
    yaw = THREE.MathUtils.clamp(yaw, lo, hi);
    aim.yaw = THREE.MathUtils.clamp(aim.yaw, lo, hi);
  }
  layoutFlat();
}
new ResizeObserver(resize).observe(stage);

/** The object being inspected: the camera moves part of the way towards it and turns to face it. */
const DOLLY = 0.12;
let focus: THREE.Vector3 | null = null;
const lastFocus = new THREE.Vector3();
let focusAmount = 0;
const baseQ = new THREE.Quaternion();
const lookQ = new THREE.Quaternion();
const euler = new THREE.Euler(0, 0, 0, "YXZ");
const look = new THREE.Matrix4();
const eye = new THREE.Vector3();
const origin = new THREE.Vector3();
const up = new THREE.Vector3(0, 1, 0);

let shown: { el: HTMLElement; at?: THREE.Vector3 }[] = [];
const projected = new THREE.Vector3();
let last = performance.now();
function frame(now: number): void {
  const dt = Math.min(0.1, (now - last) / 1000);
  last = now;
  if (current) {
    focusAmount = THREE.MathUtils.clamp(focusAmount + (focus ? dt : -dt) * 1.4, 0, 1);
    if (focus) lastFocus.copy(focus);
    const t = focusAmount * focusAmount * (3 - 2 * focusAmount);
    turn(current, dt);
    // A breath of movement while nothing is touched, so the room is a place and not a photograph.
    const sway = calm.matches || !settings().effects || drag ? 0 : Math.sin(now / 2600) * 0.004;
    euler.set(THREE.MathUtils.degToRad(current.world.pitch) + pitch + sway * 0.5, yaw + sway, 0);
    baseQ.setFromEuler(euler);
    origin.fromArray(current.world.camera ?? [0, 0, 0]);
    eye.copy(lastFocus).sub(origin).multiplyScalar((current.world.dolly ?? DOLLY) * t).add(origin);
    look.lookAt(eye, lastFocus, up);
    lookQ.setFromRotationMatrix(look);
    camera.position.copy(eye);
    camera.quaternion.copy(baseQ).slerp(lookQ, t);
    renderer.render(scene3d, camera);
    const { clientWidth: w, clientHeight: h } = stage;
    for (const s of shown) {
      if (!s.at) continue;
      projected.copy(s.at).project(camera);
      const visible = projected.z < 1 && Math.abs(projected.x) < 1.02 && Math.abs(projected.y) < 1.02;
      s.el.style.display = visible ? "" : "none";
      s.el.style.left = `${((projected.x + 1) / 2) * w}px`;
      s.el.style.top = `${((1 - projected.y) / 2) * h}px`;
    }
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

/** Ease the view towards where it was turned, within the part of the room the picture showed. */
function turn(l: Loaded, dt: number): void {
  const [lo, hi] = yawRange(l);
  if (!drag && !calm.matches) {
    // The drag's last speed carries on and dies away.
    aim.yaw += aim.yawSpeed * dt;
    aim.pitch += aim.pitchSpeed * dt;
    const fade = Math.exp(-dt * 8);
    aim.yawSpeed *= fade;
    aim.pitchSpeed *= fade;
  }
  aim.yaw = THREE.MathUtils.clamp(aim.yaw, lo, hi);
  aim.pitch = THREE.MathUtils.clamp(aim.pitch, -PITCH_RANGE, PITCH_RANGE);
  const ease = calm.matches ? 1 : 1 - Math.exp(-dt * 16);
  yaw += (aim.yaw - yaw) * ease;
  pitch += (aim.pitch - pitch) * ease;
}

// Drag to look around. The pointer is captured, so a drag that leaves the window or is taken over by the system still ends.
let drag: { id: number; x: number; y: number; at: number } | null = null;
stage.addEventListener("pointerdown", (e) => {
  if ((e.target as HTMLElement).closest("button, .subs, .prompt, .title, .about, .panel") || !current || focus) return;
  drag = { id: e.pointerId, x: e.clientX, y: e.clientY, at: performance.now() };
  aim.yawSpeed = aim.pitchSpeed = 0;
  stage.setPointerCapture(e.pointerId);
});
stage.addEventListener("pointermove", (e) => {
  if (!drag || e.pointerId !== drag.id || !current) return;
  const k = THREE.MathUtils.degToRad(camera.fov) / stage.clientHeight;
  const [dx, dy] = [(e.clientX - drag.x) * k, (e.clientY - drag.y) * k];
  const dt = Math.max(0.008, (performance.now() - drag.at) / 1000);
  aim.yaw += dx;
  aim.pitch += dy;
  // Blend towards this move's speed: one jittery sample must not fling the view.
  aim.yawSpeed = aim.yawSpeed * 0.6 + (dx / dt) * 0.4;
  aim.pitchSpeed = aim.pitchSpeed * 0.6 + (dy / dt) * 0.4;
  drag.x = e.clientX;
  drag.y = e.clientY;
  drag.at = performance.now();
  $("hint").hidden = true;
});
const endDrag = (e: PointerEvent) => {
  if (!drag || e.pointerId !== drag.id) return;
  // A pointer held still before letting go throws nothing.
  if (e.type === "pointercancel" || performance.now() - drag.at > 80) aim.yawSpeed = aim.pitchSpeed = 0;
  drag = null;
};
stage.addEventListener("pointerup", endDrag);
stage.addEventListener("pointercancel", endDrag);

// Film grain: a small noise tile, redrawn a few times a second.
const grain = $<HTMLCanvasElement>("grain");
grain.width = 160;
grain.height = 160;
const g = grain.getContext("2d")!;
const noise = g.createImageData(160, 160);
setInterval(() => {
  for (let i = 0; i < noise.data.length; i += 4) {
    const v = Math.random() * 255;
    noise.data[i] = noise.data[i + 1] = noise.data[i + 2] = v;
    noise.data[i + 3] = 255;
  }
  g.putImageData(noise, 0, 0);
}, 90);

// --- story ----------------------------------------------------------------

let vars = chapter.rt.start();
let actions: Action[] = [];
let room: string | undefined;
let flatScene: Scene | null = null;
let flatSpots: { el: HTMLElement; hotspot: Hotspot }[] = [];

function ambienceFor(scene: Scene | undefined): Ambience {
  const audio = series.game.audio;
  return (scene?.room && audio?.rooms?.[scene.room]) || audio?.default || "silence";
}

/** Touching something: its choices in the bar, the camera moving towards it. */
function inspect(s: ShownHotspot, at?: THREE.Vector3): void {
  focus = at ?? null;
  spots.classList.add("quiet");
  subs.hidden = true;
  reopen.hidden = true;
  $("hint").hidden = true;
  $("prompt-label").textContent = s.hotspot.label;
  const buttons = s.actions.map((i) => {
    const b = document.createElement("button");
    b.textContent = actions[i].label;
    b.addEventListener("click", () => act(i));
    return b;
  });
  $("prompt-actions").replaceChildren(...buttons);
  prompt.hidden = false;
}

function leaveInspect(): void {
  focus = null;
  prompt.hidden = true;
  spots.classList.remove("quiet");
  reopen.hidden = false;
}
$("prompt-cancel").addEventListener("click", leaveInspect);

function spotButton(s: ShownHotspot, at?: THREE.Vector3): HTMLButtonElement {
  const b = document.createElement("button");
  b.className = "spot";
  b.setAttribute("aria-label", s.hotspot.label);
  const name = document.createElement("span");
  name.textContent = s.hotspot.label;
  b.append(name);
  b.addEventListener("click", (e) => {
    e.stopPropagation();
    inspect(s, at);
  });
  return b;
}

/**
 * Show the passage's scene, behind a short fade to black so moving between
 * rooms reads as a step and never as a freeze; a loading line appears only if
 * the next room's world is still downloading. Returns the choices the scene
 * holds, which are found by exploring rather than read in the text.
 */
let shownScene: string | undefined;
/** The last move went through a door, which has its own sound. */
let throughDoor = false;
const veil = $<HTMLElement>("veil");
async function showScene(id: string | undefined): Promise<Set<number>> {
  const scene = id ? chapter.scenes.scenes[id] : undefined;
  throughDoor = scene?.room !== room && room !== undefined;
  if (throughDoor) door();
  room = scene?.room;
  // The first room fades in too when its world is not downloaded yet.
  const changing = shownScene !== undefined ? id !== shownScene : !!(id && worlds[id] && !settled.has(`${chapter.id}/${id}`));
  shownScene = id;
  if (changing) {
    veil.classList.add("on");
    await new Promise((r) => setTimeout(r, 380));
  }
  const waiting = setTimeout(() => veil.classList.add("waiting"), 250);
  try {
    return await setScene(id);
  } finally {
    clearTimeout(waiting);
    veil.classList.remove("waiting");
    if (changing) requestAnimationFrame(() => veil.classList.remove("on"));
  }
}

/** Put a world in the room, taking out the one there before. */
function place(next: Loaded | null): void {
  if (current === next) return;
  if (current) scene3d.remove(current.splat, ...current.figures);
  if (next) scene3d.add(next.splat, ...next.figures);
  current = next;
  yaw = pitch = aim.yaw = aim.pitch = aim.yawSpeed = aim.pitchSpeed = 0;
  if (next) resize();
}

async function setScene(id: string | undefined): Promise<Set<number>> {
  const scene = id ? chapter.scenes.scenes[id] : undefined;
  const all = scene ? hotspotsFor(scene, actions, chapter.scenes.scenes).shown : [];
  // A world with hand-placed hotspots shows only those; the rest stay text choices.
  const placed = id ? worlds[id]?.placed : undefined;
  const hot = placed ? all.filter((h) => placed.includes(h.hotspot.label)) : all;
  const onStage = new Set(hot.flatMap((h) => h.actions));
  spots.replaceChildren();
  shown = [];
  flatSpots = [];
  flatScene = null;
  focus = null;
  focusAmount = 0;
  setAmbience(ambienceFor(scene));
  if (scene && id && worlds[id]) {
    const next = await waitingOn(worlds[id], loadWorld(chapter, id));
    place(next);
    canvas.hidden = false;
    flat.hidden = true;
    for (const s of hot) {
      const at = next.anchors.get(s.hotspot.label);
      const el = spotButton(s, at);
      spots.append(el);
      shown.push({ el, at });
    }
    return onStage;
  }
  place(null);
  canvas.hidden = true;
  if (!scene) {
    flat.hidden = true;
    return onStage;
  }
  flat.src = "/" + scene.image;
  flat.hidden = false;
  await flat.decode().catch(() => undefined);
  flatScene = scene;
  for (const s of hot) {
    const el = spotButton(s);
    el.classList.add("rect");
    spots.append(el);
    flatSpots.push({ el, hotspot: s.hotspot });
  }
  layoutFlat();
  return onStage;
}

/** A `cover`-fitted picture's hotspots, laid out in pixels over the stage. */
function layoutFlat(): void {
  if (!flatScene) return;
  const [aw, ah] = flatScene.aspect;
  const { clientWidth: w, clientHeight: h } = stage;
  const s = Math.max(w / aw, h / ah);
  const box = { x: (w - aw * s) / 2, y: (h - ah * s) / 2, w: aw * s, h: ah * s };
  for (const { el, hotspot } of flatSpots) {
    const [x, y, rw, rh] = hotspot.rect;
    Object.assign(el.style, {
      left: `${box.x + (x / 100) * box.w}px`,
      top: `${box.y + (y / 100) * box.h}px`,
      width: `${(rw / 100) * box.w}px`,
      height: `${(rh / 100) * box.h}px`,
    });
  }
}

// Subtitles: one paragraph at a time; the last one offers to explore.
let segments: HTMLElement[] = [];
let shownSegment = 0;
/** The chapter is over: its last subtitle offers the next chapter. */
let ended = false;

function showSegment(n: number): void {
  shownSegment = n;
  segments.forEach((s, i) => (s.hidden = i !== n));
  // A page of the author's own (the rules, a book) gets the whole height.
  subs.classList.toggle("document", !!segments[n]?.querySelector(DOCUMENT));
  const lastOne = n >= segments.length - 1;
  subsNext.hidden = lastOne;
  subsClose.hidden = !lastOne || spots.childElementCount === 0;
  subsEnd.hidden = !lastOne || !ended;
  spots.classList.toggle("quiet", !lastOne);
  subsText.scrollTop = 0;
}

function openSubs(): void {
  subs.hidden = false;
  reopen.hidden = true;
  prompt.hidden = true;
  focus = null;
  showSegment(shownSegment);
}

subsNext.addEventListener("click", () => showSegment(shownSegment + 1));
subsClose.addEventListener("click", () => {
  subs.hidden = true;
  reopen.hidden = false;
  spots.classList.remove("quiet");
  $("hint").hidden = !current;
});
reopen.addEventListener("click", openSubs);

const DOCUMENT = ".pagina-libro, .pared, .espejo-img";

/** A page of the author's own (the rules, a book) gets a subtitle to itself, apart from the prose around it. */
function isolateDocuments(segs: HTMLElement[]): HTMLElement[] {
  const out: HTMLElement[] = [];
  for (const seg of segs) {
    const nodes = [...seg.childNodes];
    if (!nodes.some((n) => n instanceof HTMLElement && n.matches(DOCUMENT))) {
      out.push(seg);
      continue;
    }
    let part: Node[] = [];
    const flush = () => {
      if (part.some((n) => n.textContent?.trim() || (n instanceof HTMLElement && n.matches(DOCUMENT)))) {
        const s = document.createElement("tw-seg");
        s.append(...part);
        seg.before(s);
        out.push(s);
      }
      part = [];
    };
    for (const n of nodes) {
      if (n instanceof HTMLElement && n.matches(DOCUMENT)) {
        flush();
        part = [n];
        flush();
      } else part.push(n);
    }
    flush();
    seg.remove();
  }
  return out;
}

/** The passage as subtitles; a choice the scene holds is left out of the text, to be found in the room. */
function renderText(html: string, onStage: Set<number>): void {
  const passage = document.createElement("div");
  // A blank line between paragraphs becomes a single break: subtitles have no room for gaps.
  passage.innerHTML = html.replace(/<br>(\s*<br>)+/g, "<br>");
  for (const l of passage.querySelectorAll<HTMLElement>("tw-link[data-action]")) {
    if (!onStage.has(Number(l.dataset.action))) continue;
    if (l.nextSibling?.nodeName === "BR") l.nextSibling.remove();
    l.remove();
  }
  segments = isolateDocuments(segment(passage));
  subsText.replaceChildren(passage);
  passage.querySelectorAll<HTMLElement>("tw-link[data-action]").forEach((l) => l.addEventListener("click", () => act(Number(l.dataset.action))));
  shownSegment = 0;
  openSubs();
}

async function show(name: string): Promise<void> {
  try {
    // The state before the passage renders is what a resumed game starts the passage from.
    const before = structuredClone(vars);
    const page = chapter.rt.visit(vars, name);
    actions = page.actions;
    const outcome = outcomeOf(page, vars, series.carry);
    if (outcome.code) storeCode(series.id, chapter.id, outcome.code);
    remember(name, before, page.passage, outcome);
    showEnd(outcome.ended ? outcome : null);
    const sceneId = chapter.scenes.passages[page.passage];
    renderText(page.html, await showScene(sceneId));
    // As in the reader: a sting where the series marks one, else a step unless a door just sounded.
    if (isSting(series.game, chapter.id, page.passage)) sting();
    else if (!throughDoor) step();
    pulse();
    void keepAround(chapter, sceneId, page.actions);
  } catch (e) {
    subsText.textContent = (e as Error).message;
  }
}

/** Save the game here, as the reader does, and record the passage and any ending reached. */
function remember(passage: string, before: typeof vars, reached: string, outcome: Outcome): void {
  store(series.id, chapter.id, {
    passage,
    vars: before,
    undo: [],
    finished: outcome.ended,
    code: outcome.code,
    story: chapter.data.version,
  });
  storeLastPlayed(series.id, chapter.id);
  recordFound(series.id, chapter.id, { passage: reached });
  if (outcome.ended) {
    const ending = chapter.data.discoveries?.kind === "codes" ? outcome.code : reached;
    if (ending) recordFound(series.id, chapter.id, { ending });
  }
}

const HEART_BPM: Record<ConditionState["level"], number | null> = { fine: null, caution: null, danger: 84, critical: 112 };
/** The heartbeat follows the story's own condition, as in the reader; silent for a series that tracks none. */
function pulse(): void {
  const cfg = series.game.condition;
  const state = cfg ? conditionFor(series.game, vars[cfg.variable]) : undefined;
  heartbeat(state ? HEART_BPM[state.level] : null);
}

const mute = $<HTMLButtonElement>("mute");
function showMute(): void {
  const muted = settings().muted;
  mute.setAttribute("aria-pressed", String(muted));
  mute.classList.toggle("off", muted);
}
mute.addEventListener("click", () => {
  updateSettings({ muted: !settings().muted });
  unlock();
  applyVolume();
  showMute();
});
showMute();

function act(i: number): void {
  const a = actions[i];
  if (!a) return;
  prompt.hidden = true;
  if (a.kind === "link") {
    void show(a.target);
    return;
  }
  const r = chapter.rt.reveal(vars, a);
  if (r.goto) {
    void show(r.goto);
    return;
  }
  const offset = actions.length;
  actions = [...actions, ...r.actions];
  const holder = document.createElement("span");
  holder.innerHTML = r.html.replace(/data-action="(\d+)"/g, (_, n) => `data-action="${Number(n) + offset}"`);
  holder.querySelectorAll<HTMLElement>("tw-link[data-action]").forEach((l) => l.addEventListener("click", () => act(Number(l.dataset.action))));
  subsText.querySelectorAll(`tw-link[data-action="${i}"]`).forEach((l) => l.replaceWith(holder));
}

/** The end of a chapter, under its last subtitle: the code it ended on, and the way on. */
const subsEnd = $<HTMLElement>("subs-end");
const nextChapter = $<HTMLButtonElement>("subs-next-chapter");
function showEnd(outcome: Outcome | null): void {
  ended = !!outcome;
  $("subs-code").textContent = outcome?.code ? `Tu código: ${outcome.code}` : "";
  const i = series.chapters.findIndex((c) => c.id === chapter.id);
  const next = series.chapters[i + 1];
  nextChapter.hidden = !next;
  if (next) {
    nextChapter.textContent = `${chapterLabel(next)} ›`;
    nextChapter.onclick = () => void begin(next.id);
  }
}
$("subs-menu").addEventListener("click", showTitle);

// --- title -----------------------------------------------------------------

const title = $<HTMLElement>("title");
const about = $<HTMLElement>("about");
const chapterLabel = (c: ChapterSummary) => `Capítulo ${Number(c.id)}`;

/** Start a chapter from its beginning, with the previous chapter's end code carried in as the reader does. */
async function begin(id: string): Promise<void> {
  unlock();
  hideTitle();
  chapter = await loadChapter(id);
  setAuthorCss(chapter);
  document.title = `${shortName(chapter.data.title)} · borrador 3D`;
  const i = series.chapters.findIndex((c) => c.id === id);
  const previous = i > 0 ? loadCodes(series.id)[series.chapters[i - 1].id] : undefined;
  vars = withCarriedCode(freshStart(chapter.data.start, chapter.rt.start()), series.carry, previous).vars;
  await show(chapter.data.start);
}

/** Pick a chapter up where it was left; a chapter never played, or changed since, starts over. */
async function resume(id: string): Promise<void> {
  const saved = load(series.id, id);
  const next = await loadChapter(id);
  if (!saved || isStale(saved, new Set(next.rt.story.passages.map((p) => p.name)), next.data.version)) {
    await begin(id);
    return;
  }
  unlock();
  hideTitle();
  chapter = next;
  setAuthorCss(chapter);
  document.title = `${shortName(chapter.data.title)} · borrador 3D`;
  vars = withNewVariables(saved, chapter.rt.start()).vars;
  await show(saved.passage);
}

function hideTitle(): void {
  title.classList.add("gone");
  // Faded out, its buttons must not take a key press meant for the subtitles.
  title.inert = true;
  (document.activeElement as HTMLElement | null)?.blur();
}

function showTitle(): void {
  heartbeat(null);
  subs.hidden = true;
  prompt.hidden = true;
  reopen.hidden = true;
  $("hint").hidden = true;
  focus = null;
  title.inert = false;
  title.classList.remove("gone");
  buildMenu();
}

function openAbout(): void {
  about.hidden = false;
  title.inert = true;
  $<HTMLButtonElement>("about-close").focus();
}

function closeAbout(): void {
  about.hidden = true;
  title.inert = false;
}

/** The series' credits as the reader's "Acerca de" page lists them: name, role and profile links. */
function creditCards(): HTMLElement {
  const list = document.createElement("ul");
  list.className = "credits";
  for (const c of series.credits) {
    const item = document.createElement("li");
    item.className = "credit";
    const name = document.createElement("span");
    name.className = "credit-name";
    name.textContent = c.name;
    const role = document.createElement("span");
    role.className = "credit-role";
    role.textContent = c.role;
    item.append(name, role);
    const links = Object.entries(c.links);
    if (links.length) {
      const span = document.createElement("span");
      span.className = "credit-links";
      links.forEach(([label, url], n) => {
        const a = document.createElement("a");
        a.href = url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.textContent = label;
        span.append(...(n ? [" · ", a] : [a]));
      });
      item.append(span);
    }
    list.append(item);
  }
  return list;
}

// --- the title's menu: the reader's own, over the first room ----------------

const panel = $<HTMLElement>("panel");
const panelBody = $<HTMLElement>("panel-body");
/** An element with a class and its children: what every panel below is built from. */
function make(tag: string, props: { className?: string; htmlFor?: string } = {}, ...children: (Node | string)[]): HTMLElement {
  const node = document.createElement(tag);
  if (props.className) node.className = props.className;
  if (props.htmlFor) node.setAttribute("for", props.htmlFor);
  node.append(...children);
  return node;
}
const chapterName = (c: ChapterSummary) => `${chapterLabel(c)} · ${shortName(c.title)}`;

function openPanel(heading: string, ...content: Node[]): void {
  $("panel-title").textContent = heading;
  panelBody.replaceChildren(...content);
  panel.hidden = false;
  panel.scrollTop = 0;
  title.inert = true;
  title.classList.add("behind");
  // The close button is last: focusing it must not scroll the panel past its start.
  $<HTMLButtonElement>("panel-close").focus({ preventScroll: true });
}

function closePanel(): void {
  panel.hidden = true;
  title.inert = false;
  title.classList.remove("behind");
}
$("panel-close").addEventListener("click", closePanel);

function menuButton(label: string, note: string | null, onClick: () => void): HTMLButtonElement {
  const b = make("button", { className: "title-start" }, label) as HTMLButtonElement;
  if (note) b.append(" ", make("span", { className: "title-chapter" }, note));
  b.addEventListener("click", onClick);
  return b;
}

/** "Nueva partida" wipes chapter 1's progress, so it asks with a second tap (embedded viewers block confirm()). */
function newGameButton(first: ChapterSummary): HTMLButtonElement {
  const started = !!load(series.id, first.id);
  const b = menuButton(started ? "Nueva partida" : "Empezar", null, () => {
    if (started && !b.dataset.armed) {
      b.dataset.armed = "1";
      b.textContent = "¿Borrar la partida? Toca otra vez";
      setTimeout(() => {
        if (!b.isConnected) return;
        delete b.dataset.armed;
        b.textContent = "Nueva partida";
      }, 4000);
      return;
    }
    clear(series.id, first.id);
    void begin(first.id);
  });
  return b;
}

function chapterState(c: ChapterSummary): string {
  const saved = load(series.id, c.id);
  return saved?.finished ? "Terminado" : saved ? "En curso" : "Sin empezar";
}

function openChapters(): void {
  const list = make("div", { className: "title-menu" });
  for (const c of series.chapters) {
    const b = menuButton(chapterName(c), `· ${chapterState(c)}`, () => {
      closePanel();
      void resume(c.id);
    });
    b.dataset.chapter = c.id;
    list.append(b);
  }
  openPanel("Capítulos", list);
}

async function openAchievements(): Promise<void> {
  const all = await Promise.all(series.chapters.map((c) => loadChapter(c.id)));
  const found = loadFound(series.id);
  const finished = new Set(series.chapters.filter((c) => load(series.id, c.id)?.finished).map((c) => c.id));
  const chapters = series.chapters.map((c, i) => ({ id: c.id, title: shortName(c.title), discoveries: all[i].data.discoveries }));
  const blocks = chapters
    .filter((c) => c.discoveries)
    .map((c) => {
      const sum = summarize(c.discoveries!, found[c.id] ?? { endings: [], passages: [] });
      const endings = make("div", { className: "endings" }, ...sum.endings.map((e) => make("span", { className: e ? "ending found" : "ending" }, e ?? "???")));
      return make(
        "section",
        { className: "ach-chapter" },
        make("h3", {}, c.title),
        make("p", {}, `Finales: ${sum.endingsFound} de ${sum.endings.length} · Rincones explorados: ${sum.passagesSeen} de ${sum.passagesTotal}`),
        endings,
      );
    });
  const list = make(
    "ul",
    { className: "ach-list" },
    ...achievements(chapters, found, finished).map((a) => make("li", { className: a.done ? "ach done" : "ach" }, `${a.done ? "◆" : "◇"} ${a.title}`)),
  );
  openPanel("Finales y logros", ...blocks, make("h3", {}, "Logros"), list);
}

function choice<K extends keyof Settings>(label: string, key: K, options: [Settings[K], string][]): HTMLElement {
  const group = make("fieldset", { className: "setting" }, make("legend", {}, label));
  for (const [value, text] of options) {
    const input = document.createElement("input");
    input.type = "radio";
    input.name = key;
    input.checked = settings()[key] === value;
    input.addEventListener("change", () => {
      updateSettings({ [key]: value } as Partial<Settings>);
      showMute();
    });
    const label = document.createElement("label");
    label.append(input, ` ${text}`);
    group.append(label);
  }
  return group;
}

function openSettingsPanel(): void {
  const volume = document.createElement("input");
  Object.assign(volume, { type: "range", min: "0", max: "100", value: String(Math.round(settings().volume * 100)), id: "setting-volume" });
  volume.addEventListener("input", () => {
    updateSettings({ volume: Number(volume.value) / 100 });
    unlock();
    applyVolume();
  });
  openPanel(
    "Ajustes",
    make("div", { className: "setting" }, make("label", { htmlFor: "setting-volume" }, "Volumen"), volume),
    choice("Sonido", "muted", [[false, "Activado"], [true, "Silenciado"]]),
    choice("Tamaño del texto", "textSize", [["s", "Pequeño"], ["m", "Normal"], ["l", "Grande"]]),
    choice("Efectos (grano, parpadeo y balanceo)", "effects", [[true, "Sí"], [false, "No"]]),
  );
}

/** The menu, rebuilt each time the title shows, since what "Continuar" offers changes as the reader plays. */
const menu = $<HTMLElement>("title-menu");
function buildMenu(): void {
  const last = lastPlayed();
  const lastChapter = last?.series === series.id ? series.chapters.find((c) => c.id === last.chapter) : undefined;
  const first = series.chapters[0];
  // One way in stands out — where the reader left off, or the beginning — and the rest step back.
  const play = make("button", { className: "title-play" }) as HTMLButtonElement;
  if (lastChapter) {
    play.append("Continuar", make("span", { className: "title-play-note" }, chapterName(lastChapter)));
    play.addEventListener("click", () => void resume(lastChapter.id));
  } else if (first) {
    play.append("Empezar", make("span", { className: "title-play-note" }, chapterName(first)));
    play.addEventListener("click", () => void begin(first.id));
  }
  $("title-primary").replaceChildren(play);
  menu.replaceChildren(
    ...(lastChapter && first ? [newGameButton(first)] : []),
    Object.assign(menuButton("Capítulos", null, openChapters), { id: "menu-chapters" }),
    menuButton("Finales y logros", null, () => void openAchievements()),
    menuButton("Ajustes", null, openSettingsPanel),
    ...(series.credits.length || series.about.length ? [Object.assign(menuButton("Créditos", null, openAbout), { id: "menu-credits" })] : []),
  );
}
applySettings();
buildMenu();
// The author under the title, as a book's cover has it; the rest of the credits are one tap away.
const author = series.credits[0];
$("title-byline").textContent = author ? `${author.role} · ${author.name}` : "";
$("about-series").textContent = series.title;
$("about-body").replaceChildren(
  ...(series.credits.length ? [creditCards()] : []),
  ...series.about.map((text) => Object.assign(document.createElement("p"), { textContent: text })),
  // What only this 3D version adds; the series' own notes describe the pictures.
  Object.assign(document.createElement("p"), {
    textContent:
      "En esta versión 3D, cada sala es un mundo generado con World Labs (Marble) a partir de su imagen, y los personajes se recortan de esas imágenes para que se vean nítidos. Se muestra en el navegador con three.js y Spark.",
  }),
);
$("about-close").addEventListener("click", closeAbout);

// The first chapter's first room loads behind the title; starting is the gesture that unlocks sound.
const firstScene = chapter.scenes.passages[chapter.data.start];
if (firstScene && worlds[firstScene]) {
  void waitingOn(worlds[firstScene], loadWorld(chapter, firstScene))
    .then((l) => {
      if (shownScene === undefined) place(l);
    })
    .catch(() => undefined);
}

// The reader's keys: Space or Enter reads on (and, after the last paragraph, explores); Escape steps back.
addEventListener("keydown", (ev) => {
  const t = ev.target as HTMLElement;
  if (ev.key === "Escape") {
    if (!panel.hidden) closePanel();
    else if (!about.hidden) closeAbout();
    else if (!prompt.hidden) leaveInspect();
    return;
  }
  if ((ev.key !== " " && ev.key !== "Enter") || t.closest?.("tw-link, input, button, a")) return;
  if (!title.inert) {
    ev.preventDefault();
    const last = lastPlayed();
    void (last?.series === series.id ? resume(last.chapter) : begin(series.chapters[0].id));
    return;
  }
  if (!about.hidden || !panel.hidden) return;
  ev.preventDefault();
  if (!subs.hidden) [subsNext, subsClose].find((b) => !b.hidden)?.click();
  else if (!reopen.hidden) openSubs();
});

// Safari's own gestures still zoom past touch-action in places: stop them outright.
for (const type of ["gesturestart", "gesturechange", "dblclick"]) {
  document.addEventListener(type, (e) => e.preventDefault(), { passive: false });
}
