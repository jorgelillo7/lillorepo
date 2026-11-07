/**
 * 3D draft of a chapter: the reader's own engine runs the passages; a scene
 * with a generated world (worlds.json) is shown as a Gaussian-splat room whose
 * hotspots are projected from the 2D scene file onto the world's collider, and
 * any other scene falls back to its 2D picture.
 */

import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import type { ChapterData } from "../../src/contract.ts";
import { Runtime, type Action } from "../../src/engine/runtime.ts";
import { hotspotsFor, type Hotspot, type Scene, type ShownHotspot } from "../../src/engine/scenes.ts";

interface World {
  splats: string;
  collider: string;
  /** Fraction of the picture's width and height trimmed from each edge before generation. */
  crop: [number, number];
  /** Vertical field of view and downward pitch, in degrees, that reproduce the scene image. */
  fovY: number;
  pitch: number;
}

const $ = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
const canvas = $<HTMLCanvasElement>("world");
const flat = $<HTMLImageElement>("flat");
const spots = $<HTMLDivElement>("spots");
const text = $<HTMLElement>("text");
const stage = $<HTMLElement>("stage");

const [data, worlds] = await Promise.all([
  fetch("/01.json").then((r) => r.json() as Promise<ChapterData>),
  fetch("/worlds.json").then((r) => r.json() as Promise<Record<string, World>>),
]);
const scenes = data.scenes!;
const rt = new Runtime(data);
document.title = `Borrador 3D · ${data.title}`;

// --- 3D -------------------------------------------------------------------

const renderer = new THREE.WebGLRenderer({ canvas, antialias: false });
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
const scene3d = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(46, 1, 0.01, 200);
camera.rotation.order = "YXZ";
scene3d.add(new SparkRenderer({ renderer }));
/** Marble worlds use OpenCV axes (y down, z forward); three.js has y up, z back. */
const OPENCV_TO_THREE = new THREE.Quaternion(1, 0, 0, 0);

interface Loaded {
  id: string;
  world: World;
  splat: SplatMesh;
  collider: THREE.Object3D;
  anchors: Map<string, THREE.Vector3>;
}
const loaded = new Map<string, Promise<Loaded>>();
let current: Loaded | null = null;
let yaw = 0;
let pitch = 0;

function loadWorld(id: string, world: World, scene: Scene): Promise<Loaded> {
  let p = loaded.get(id);
  if (!p) {
    p = (async () => {
      const splat = new SplatMesh({ url: "/" + world.splats });
      splat.quaternion.copy(OPENCV_TO_THREE);
      const gltf = await new GLTFLoader().loadAsync("/" + world.collider);
      const collider = gltf.scene;
      collider.quaternion.copy(OPENCV_TO_THREE);
      collider.updateMatrixWorld(true);
      await splat.initialized;
      return { id, world, splat, collider, anchors: anchorsFor(world, scene, collider) };
    })();
    loaded.set(id, p);
  }
  return p;
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
  cam.updateMatrixWorld(true);
  const ray = new THREE.Raycaster();
  const anchors = new Map<string, THREE.Vector3>();
  for (const spot of scene.hotspots) {
    const [x, y, rw, rh] = spot.rect;
    const u = ((x + rw / 2) / 100 - cx) / (1 - 2 * cx);
    const v = ((y + rh / 2) / 100 - cy) / (1 - 2 * cy);
    ray.setFromCamera(new THREE.Vector2(u * 2 - 1, 1 - v * 2), cam);
    const hit = ray.intersectObject(collider, true)[0];
    anchors.set(spot.label, hit ? hit.point.clone() : ray.ray.at(2, new THREE.Vector3()));
  }
  return anchors;
}

function resize(): void {
  const { clientWidth: w, clientHeight: h } = stage;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.fov = current ? fovFor(current, camera.aspect) : 46;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(stage);

/**
 * The vertical field of view that keeps the picture's whole width in view on a
 * narrower stage (capped, so a phone in portrait looks around instead of warping).
 */
function fovFor(l: Loaded, aspect: number): number {
  const picture = pictureAspect(scenes.scenes[l.id], l.world);
  if (aspect >= picture) return l.world.fovY;
  const halfTan = Math.tan(THREE.MathUtils.degToRad(l.world.fovY / 2)) * picture;
  return Math.min(90, THREE.MathUtils.radToDeg(2 * Math.atan(halfTan / aspect)));
}

let shown: { el: HTMLElement; at?: THREE.Vector3 }[] = [];
const v = new THREE.Vector3();
function frame(): void {
  if (current) {
    camera.rotation.y = yaw;
    camera.rotation.x = THREE.MathUtils.degToRad(current.world.pitch) + pitch;
    renderer.render(scene3d, camera);
    const { clientWidth: w, clientHeight: h } = stage;
    for (const s of shown) {
      if (!s.at) continue;
      v.copy(s.at).project(camera);
      const visible = v.z < 1 && Math.abs(v.x) < 1.05 && Math.abs(v.y) < 1.05;
      s.el.style.display = visible ? "" : "none";
      s.el.style.left = `${((v.x + 1) / 2) * w}px`;
      s.el.style.top = `${((1 - v.y) / 2) * h}px`;
    }
  }
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// Drag to look around, within the part of the room the picture showed.
let drag: { x: number; y: number; yaw: number; pitch: number } | null = null;
stage.addEventListener("pointerdown", (e) => {
  if ((e.target as HTMLElement).closest(".spot, .menu")) return;
  closeMenu();
  drag = { x: e.clientX, y: e.clientY, yaw, pitch };
});
addEventListener("pointermove", (e) => {
  if (!drag || !current) return;
  const k = THREE.MathUtils.degToRad(camera.fov) / stage.clientHeight;
  yaw = THREE.MathUtils.clamp(drag.yaw + (e.clientX - drag.x) * k, -0.9, 0.9);
  pitch = THREE.MathUtils.clamp(drag.pitch + (e.clientY - drag.y) * k, -0.35, 0.35);
  $("hint").hidden = true;
});
addEventListener("pointerup", () => (drag = null));

// --- story ----------------------------------------------------------------

let vars = rt.start();
let actions: Action[] = [];
let menu: HTMLElement | null = null;

function closeMenu(): void {
  menu?.remove();
  menu = null;
}

function spotButton(s: ShownHotspot): HTMLButtonElement {
  const b = document.createElement("button");
  b.className = "spot";
  b.textContent = s.hotspot.label;
  b.addEventListener("click", (e) => {
    e.stopPropagation();
    if (s.actions.length === 1) return act(s.actions[0]);
    closeMenu();
    menu = document.createElement("div");
    menu.className = "menu";
    menu.style.left = b.style.left || `${b.offsetLeft + b.offsetWidth / 2}px`;
    menu.style.top = b.style.top || `${b.offsetTop + b.offsetHeight}px`;
    for (const i of s.actions) {
      const o = document.createElement("button");
      o.textContent = actions[i].label;
      o.addEventListener("click", () => act(i));
      menu.append(o);
    }
    spots.append(menu);
  });
  return b;
}

async function showScene(id: string | undefined): Promise<ShownHotspot[]> {
  const scene = id ? scenes.scenes[id] : undefined;
  const { shown: hot } = scene ? hotspotsFor(scene, actions, scenes.scenes) : { shown: [] };
  spots.replaceChildren();
  shown = [];
  closeMenu();
  const world = id ? worlds[id] : undefined;
  if (scene && world) {
    $("loading").hidden = false;
    const next = await loadWorld(id!, world, scene);
    $("loading").hidden = true;
    if (current?.id !== next.id) {
      if (current) scene3d.remove(current.splat);
      scene3d.add(next.splat);
      current = next;
      yaw = 0;
      pitch = 0;
      resize();
    }
    canvas.hidden = false;
    flat.hidden = true;
    for (const s of hot) {
      const el = spotButton(s);
      spots.append(el);
      shown.push({ el, at: next.anchors.get(s.hotspot.label) });
    }
    $("hint").hidden = false;
    return hot;
  }
  current = null;
  canvas.hidden = true;
  $("hint").hidden = true;
  if (!scene) {
    flat.hidden = true;
    return hot;
  }
  flat.src = "/" + scene.image;
  flat.hidden = false;
  await flat.decode().catch(() => undefined);
  const box = fitted(scene, stage.clientWidth, stage.clientHeight);
  for (const s of hot) {
    const el = spotButton(s);
    el.classList.add("rect");
    place(el, s.hotspot, box);
    spots.append(el);
    shown.push({ el });
  }
  return hot;
}

/** The rectangle a `contain`-fitted picture occupies in the stage. */
function fitted(scene: Scene, w: number, h: number) {
  const [aw, ah] = scene.aspect;
  const s = Math.min(w / aw, h / ah);
  return { x: (w - aw * s) / 2, y: (h - ah * s) / 2, w: aw * s, h: ah * s };
}

function place(el: HTMLElement, h: Hotspot, box: { x: number; y: number; w: number; h: number }): void {
  const [x, y, w, hh] = h.rect;
  Object.assign(el.style, {
    left: `${box.x + (x / 100) * box.w}px`,
    top: `${box.y + (y / 100) * box.h}px`,
    width: `${(w / 100) * box.w}px`,
    height: `${(hh / 100) * box.h}px`,
  });
}

/** The passage's text; its choices stay clickable there too, whether or not the room shows them. */
function renderText(html: string): void {
  text.innerHTML = `<div class="passage">${html}</div>`;
  text.querySelectorAll<HTMLElement>("tw-link[data-action]").forEach((l) => l.addEventListener("click", () => act(Number(l.dataset.action))));
  text.scrollTop = 0;
}

async function show(name: string): Promise<void> {
  try {
    const page = rt.visit(vars, name);
    actions = page.actions;
    await showAndRemember(scenes.passages[page.passage]);
    renderText(page.html);
  } catch (e) {
    text.innerHTML = `<p class="error">${(e as Error).message}</p>`;
  }
}

function act(i: number): void {
  closeMenu();
  const a = actions[i];
  if (!a) return;
  if (a.kind === "link") {
    void show(a.target);
    return;
  }
  const r = rt.reveal(vars, a);
  if (r.goto) {
    void show(r.goto);
    return;
  }
  const offset = actions.length;
  actions = [...actions, ...r.actions];
  const html = r.html.replace(/data-action="(\d+)"/g, (_, n) => `data-action="${Number(n) + offset}"`);
  const holder = document.createElement("div");
  holder.innerHTML = html;
  holder.querySelectorAll<HTMLElement>("tw-link[data-action]").forEach((l) => l.addEventListener("click", () => act(Number(l.dataset.action))));
  text.querySelectorAll(`tw-link[data-action="${i}"]`).forEach((l) => l.replaceWith(holder));
}

// A flat picture's hotspots are laid out in pixels: lay them out again when the stage changes size.
let lastFlat: { id: string } | null = null;
async function showAndRemember(id: string | undefined): Promise<ShownHotspot[]> {
  lastFlat = id && !worlds[id] ? { id } : null;
  return showScene(id);
}
new ResizeObserver(() => {
  if (!lastFlat || !scenes.scenes[lastFlat.id]) return;
  const box = fitted(scenes.scenes[lastFlat.id], stage.clientWidth, stage.clientHeight);
  const hot = hotspotsFor(scenes.scenes[lastFlat.id], actions, scenes.scenes).shown;
  shown.forEach((s, n) => hot[n] && place(s.el, hot[n].hotspot, box));
}).observe(stage);

void show(data.start);
