/**
 * 3D draft of a chapter: the reader's own engine runs the passages; a scene
 * with a generated world (worlds.json) is shown as a Gaussian-splat room whose
 * hotspots are projected from the 2D scene file onto the world's collider, and
 * any other scene falls back to its 2D picture. The passage reads as
 * subtitles, a paragraph at a time; touching something opens its choices and
 * moves the camera towards it.
 */

import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { door, setAmbience, unlock } from "../../src/app/audio.ts";
import { segment } from "../../src/app/pacing.ts";
import { freshStart, outcomeOf, withCarriedCode, type Outcome } from "../../src/app/progression.ts";
import { loadCodes, storeCode } from "../../src/app/save.ts";
import type { ChapterData, ChapterSummary, SeriesEntry } from "../../src/contract.ts";
import type { Ambience } from "../../src/engine/game.ts";
import { Runtime, type Action } from "../../src/engine/runtime.ts";
import { hotspotsFor, type Hotspot, type Scene, type SceneFile, type ShownHotspot } from "../../src/engine/scenes.ts";

interface World {
  splats: string;
  collider: string;
  /** Fraction of the picture's width and height trimmed from each edge before generation. */
  crop: [number, number];
  /** Vertical field of view and downward pitch, in degrees, that reproduce the scene image. */
  fovY: number;
  pitch: number;
  /**
   * How far the view's edges may turn, in degrees from straight ahead (right
   * negative, left positive): past them the world shows what it invented
   * beyond the picture — a door that is not there, say. Default: 10° past
   * the picture's own edges.
   */
  bounds?: [number, number];
  /**
   * Characters kept out of the world and laid back in as sharp cut-outs from
   * the picture (`rect` in percent of the picture, like a hotspot): a world
   * bakes a person in soft and breaks them up seen close.
   */
  figures?: { image: string; rect: [number, number, number, number] }[];
  /** How far the camera moves towards what is inspected (default DOLLY); 0 where a cut-out must stay aligned with the room. */
  dolly?: number;
  /** Where the camera stands, when the world did not grow from the picture's own viewpoint. */
  camera?: [number, number, number];
  /**
   * Hotspots placed by hand, as fractions of this world's own view; when set,
   * a hotspot not listed has no place in the room and stays a text choice.
   */
  anchors?: Record<string, [number, number]>;
}

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

const [library, worlds] = await Promise.all([
  fetch("/library.json").then((r) => r.json() as Promise<SeriesEntry[]>),
  fetch("/worlds.json").then((r) => r.json() as Promise<Record<string, World>>),
]);
const series = library[0];
/** The build stamp prepare.ts adds, appended to world files so a cached older one is never used. */
const BUILD = (worlds as unknown as Record<string, { build?: number }>)[""]?.build ?? 0;
delete (worlds as Record<string, unknown>)[""];
const fresh = (path: string) => `/${path}?v=${BUILD}`;

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
if ((navigator as Navigator & { standalone?: boolean }).standalone || matchMedia("(display-mode: fullscreen), (display-mode: standalone)").matches) {
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

interface Loaded {
  id: string;
  /** The world's scene as the playing chapter has it: its hotspots, and so its anchors, differ between chapters. */
  scene: Scene;
  world: World;
  splat: SplatMesh;
  figures: THREE.Object3D[];
  anchors: Map<string, THREE.Vector3>;
}
/** A world's downloads by splat file, shared by every chapter and every scene that shows its room. */
const assets = new Map<string, Promise<{ splat: SplatMesh; collider: THREE.Object3D }>>();
/** A world as one chapter shows it, by "chapter/scene"; `settled` holds those ready to show at once. */
const loaded = new Map<string, Promise<Loaded>>();
const settled = new Set<string>();
let current: Loaded | null = null;
let yaw = 0;
let pitch = 0;

function loadAssets(world: World): Promise<{ splat: SplatMesh; collider: THREE.Object3D }> {
  let p = assets.get(world.splats);
  if (!p) {
    p = (async () => {
      const splat = new SplatMesh({ url: fresh(world.splats) });
      splat.quaternion.copy(OPENCV_TO_THREE);
      const collider = (await new GLTFLoader().loadAsync(fresh(world.collider))).scene;
      collider.quaternion.copy(OPENCV_TO_THREE);
      collider.updateMatrixWorld(true);
      await splat.initialized;
      return { splat, collider };
    })();
    assets.set(world.splats, p);
  }
  return p;
}

function loadWorld(c: Chapter, id: string): Promise<Loaded> {
  const key = `${c.id}/${id}`;
  let p = loaded.get(key);
  if (!p) {
    const world = worlds[id];
    const scene = c.scenes.scenes[id];
    p = (async () => {
      const { splat, collider } = await loadAssets(world);
      const figures = await Promise.all((world.figures ?? []).map((f) => figure(world, scene, collider, f)));
      settled.add(key);
      return { id, scene, world, splat, figures, anchors: anchorsFor(world, scene, collider) };
    })();
    loaded.set(key, p);
  }
  return p;
}

/** The picture's camera, as the world's starting view reproduces it. */
function pictureCamera(world: World, scene: Scene): THREE.PerspectiveCamera {
  const cam = new THREE.PerspectiveCamera(world.fovY, pictureAspect(scene, world), 0.01, 200);
  cam.rotation.order = "YXZ";
  cam.rotation.x = THREE.MathUtils.degToRad(world.pitch);
  cam.position.fromArray(world.camera ?? [0, 0, 0]);
  cam.updateMatrixWorld(true);
  return cam;
}

/** A point of the picture (fractions of the trimmed view) as normalised device coordinates. */
function ndc(world: World, xPct: number, yPct: number): THREE.Vector2 {
  const [cx, cy] = world.crop;
  const u = (xPct / 100 - cx) / (1 - 2 * cx);
  const v = (yPct / 100 - cy) / (1 - 2 * cy);
  return new THREE.Vector2(u * 2 - 1, 1 - v * 2);
}

/**
 * A cut-out laid into the room: a quad facing the picture's camera at the
 * depth of what lies under its centre (the bed, for someone lying on it), sized
 * so that from that camera it covers exactly its rectangle of the picture.
 */
async function figure(world: World, scene: Scene, collider: THREE.Object3D, f: NonNullable<World["figures"]>[number]): Promise<THREE.Object3D> {
  const cam = pictureCamera(world, scene);
  const [x, y, w, h] = f.rect;
  const ray = new THREE.Raycaster();
  ray.setFromCamera(ndc(world, x + w / 2, y + h / 2), cam);
  const hit = ray.intersectObject(collider, true)[0];
  const at = hit ? hit.point : ray.ray.at(2, new THREE.Vector3());
  const depth = at.clone().applyMatrix4(cam.matrixWorldInverse).z;
  const corner = (px: number, py: number) => {
    const p = ndc(world, px, py);
    const v = new THREE.Vector3(p.x, p.y, 0.5).unproject(cam).applyMatrix4(cam.matrixWorldInverse);
    return v.multiplyScalar(depth / v.z).applyMatrix4(cam.matrixWorld);
  };
  const [tl, tr, bl, br] = [corner(x, y), corner(x + w, y), corner(x, y + h), corner(x + w, y + h)];
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.Float32BufferAttribute([...tl.toArray(), ...tr.toArray(), ...bl.toArray(), ...br.toArray()], 3));
  geometry.setAttribute("uv", new THREE.Float32BufferAttribute([0, 1, 1, 1, 0, 0, 1, 0], 2));
  geometry.setIndex([0, 2, 1, 1, 2, 3]);
  const texture = await new THREE.TextureLoader().loadAsync(fresh(f.image));
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

/** Where each hotspot's centre lands in the room: a ray from the camera that reproduces the image, cast onto the collider. */
function anchorsFor(world: World, scene: Scene, collider: THREE.Object3D): Map<string, THREE.Vector3> {
  const [cx, cy] = world.crop;
  const cam = new THREE.PerspectiveCamera(world.fovY, pictureAspect(scene, world), 0.01, 200);
  cam.rotation.order = "YXZ";
  cam.rotation.x = THREE.MathUtils.degToRad(world.pitch);
  cam.position.fromArray(world.camera ?? [0, 0, 0]);
  cam.updateMatrixWorld(true);
  const ray = new THREE.Raycaster();
  const anchors = new Map<string, THREE.Vector3>();
  for (const spot of scene.hotspots) {
    const [x, y, rw, rh] = spot.rect;
    const placed = world.anchors?.[spot.label];
    if (world.anchors && !placed) continue;
    const u = placed ? placed[0] : ((x + rw / 2) / 100 - cx) / (1 - 2 * cx);
    const v = placed ? placed[1] : ((y + rh / 2) / 100 - cy) / (1 - 2 * cy);
    ray.setFromCamera(new THREE.Vector2(u * 2 - 1, 1 - v * 2), cam);
    const hit = ray.intersectObject(collider, true)[0];
    anchors.set(spot.label, hit ? hit.point.clone() : ray.ray.at(2, new THREE.Vector3()));
  }
  return anchors;
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
    euler.set(THREE.MathUtils.degToRad(current.world.pitch) + pitch, yaw, 0);
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

// Drag to look around, within the part of the room the picture showed.
let drag: { x: number; y: number; yaw: number; pitch: number } | null = null;
stage.addEventListener("pointerdown", (e) => {
  if ((e.target as HTMLElement).closest("button, .subs, .prompt, .title, .about")) return;
  drag = { x: e.clientX, y: e.clientY, yaw, pitch };
});
addEventListener("pointermove", (e) => {
  if (!drag || !current || focus) return;
  const k = THREE.MathUtils.degToRad(camera.fov) / stage.clientHeight;
  const [lo, hi] = yawRange(current);
  yaw = THREE.MathUtils.clamp(drag.yaw + (e.clientX - drag.x) * k, lo, hi);
  pitch = THREE.MathUtils.clamp(drag.pitch + (e.clientY - drag.y) * k, -0.35, 0.35);
  $("hint").hidden = true;
});
addEventListener("pointerup", () => (drag = null));

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
const veil = $<HTMLElement>("veil");
async function showScene(id: string | undefined): Promise<Set<number>> {
  const scene = id ? chapter.scenes.scenes[id] : undefined;
  if (scene?.room !== room) {
    if (room !== undefined) door();
    room = scene?.room;
  }
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
  yaw = 0;
  pitch = 0;
  if (next) resize();
}

async function setScene(id: string | undefined): Promise<Set<number>> {
  const scene = id ? chapter.scenes.scenes[id] : undefined;
  const all = scene ? hotspotsFor(scene, actions, chapter.scenes.scenes).shown : [];
  // A world with hand-placed hotspots shows only those; the rest stay text choices.
  const placed = id && worlds[id]?.anchors;
  const hot = placed ? all.filter((h) => h.hotspot.label in placed) : all;
  const onStage = new Set(hot.flatMap((h) => h.actions));
  spots.replaceChildren();
  shown = [];
  flatSpots = [];
  flatScene = null;
  focus = null;
  focusAmount = 0;
  setAmbience(ambienceFor(scene));
  if (scene && id && worlds[id]) {
    const next = await loadWorld(chapter, id);
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
    const page = chapter.rt.visit(vars, name);
    actions = page.actions;
    const outcome = outcomeOf(page, vars, series.carry);
    if (outcome.code) storeCode(series.id, chapter.id, outcome.code);
    showEnd(outcome.ended ? outcome : null);
    renderText(page.html, await showScene(chapter.scenes.passages[page.passage]));
  } catch (e) {
    subsText.textContent = (e as Error).message;
  }
}

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
  // The chapter's other rooms download in the background, so stepping into one is usually instant.
  const c = chapter;
  for (const scene of Object.keys(c.scenes.scenes)) {
    if (worlds[scene]) await loadWorld(c, scene).catch(() => undefined);
  }
}

function hideTitle(): void {
  title.classList.add("gone");
  // Faded out, its buttons must not take a key press meant for the subtitles.
  title.inert = true;
  (document.activeElement as HTMLElement | null)?.blur();
}

function showTitle(): void {
  subs.hidden = true;
  prompt.hidden = true;
  reopen.hidden = true;
  $("hint").hidden = true;
  focus = null;
  title.inert = false;
  title.classList.remove("gone");
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

// The title's menu: each chapter, then "Acerca de"; the credits line under the warning opens it too.
const menu = $<HTMLElement>("title-menu");
for (const c of series.chapters) {
  const b = document.createElement("button");
  b.className = "title-start";
  b.dataset.chapter = c.id;
  b.innerHTML = `${chapterLabel(c)} <span class="title-chapter"></span>`;
  b.querySelector("span")!.textContent = `· ${shortName(c.title)}`;
  b.addEventListener("click", () => void begin(c.id));
  menu.append(b);
}
if (series.credits.length || series.about.length) {
  const b = document.createElement("button");
  b.className = "title-start";
  b.textContent = "Acerca de";
  b.addEventListener("click", openAbout);
  menu.append(b);
}
const credits = $<HTMLButtonElement>("title-credits");
credits.textContent = series.credits.map((c) => `${c.role}: ${c.name}`).join(" · ");
credits.hidden = !series.credits.length;
credits.addEventListener("click", openAbout);
$("about-series").textContent = series.title;
$("about-body").replaceChildren(
  ...(series.credits.length ? [creditCards()] : []),
  ...series.about.map((text) => Object.assign(document.createElement("p"), { textContent: text })),
);
$("about-close").addEventListener("click", closeAbout);

// The first chapter's first room loads behind the title; starting is the gesture that unlocks sound.
const firstScene = chapter.scenes.passages[chapter.data.start];
if (firstScene && worlds[firstScene]) {
  void loadWorld(chapter, firstScene).then((l) => {
    if (shownScene === undefined) place(l);
  });
}

// The reader's keys: Space or Enter reads on (and, after the last paragraph, explores); Escape steps back.
addEventListener("keydown", (ev) => {
  const t = ev.target as HTMLElement;
  if (ev.key === "Escape") {
    if (!about.hidden) closeAbout();
    else if (!prompt.hidden) leaveInspect();
    return;
  }
  if ((ev.key !== " " && ev.key !== "Enter") || t.closest?.("tw-link, input, button, a")) return;
  if (!title.inert) {
    ev.preventDefault();
    void begin(series.chapters[0].id);
    return;
  }
  if (!about.hidden) return;
  ev.preventDefault();
  if (!subs.hidden) [subsNext, subsClose].find((b) => !b.hidden)?.click();
  else if (!reopen.hidden) openSubs();
});

// Safari's own gestures still zoom past touch-action in places: stop them outright.
for (const type of ["gesturestart", "gesturechange", "dblclick"]) {
  document.addEventListener(type, (e) => e.preventDefault(), { passive: false });
}
