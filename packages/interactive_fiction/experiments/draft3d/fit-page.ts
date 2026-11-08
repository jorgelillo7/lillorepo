/**
 * The page fit.ts drives: renders a world from a given camera and scores the
 * frame against the picture it was generated from (grey-level correlation,
 * 1 = identical). Not part of the draft itself.
 */

import { SparkRenderer, SplatMesh } from "@sparkjsdev/spark";
import * as THREE from "three";

const W = 320;
const p = new URLSearchParams(location.search);
const [cx, cy] = (p.get("crop") ?? "0,0").split(",").map(Number);
const picture = new Image();
picture.src = "/" + p.get("picture");
await picture.decode();
const pw = picture.naturalWidth * (1 - 2 * cx);
const ph = picture.naturalHeight * (1 - 2 * cy);
const H = Math.round((W * ph) / pw);

const canvas = document.getElementById("c") as HTMLCanvasElement;
const renderer = new THREE.WebGLRenderer({ canvas, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(W, H, false);
const scene = new THREE.Scene();
scene.add(new SparkRenderer({ renderer }));
const splat = new SplatMesh({ url: "/" + p.get("splats") });
splat.quaternion.set(1, 0, 0, 0); // OpenCV axes → three.js
scene.add(splat);
await splat.initialized;
const camera = new THREE.PerspectiveCamera(46, W / H, 0.01, 200);
camera.rotation.order = "YXZ";

function grey(source: CanvasImageSource, sx: number, sy: number, sw: number, sh: number): Float32Array {
  const c = document.createElement("canvas");
  c.width = W;
  c.height = H;
  const g = c.getContext("2d")!;
  g.drawImage(source, sx, sy, sw, sh, 0, 0, W, H);
  const d = g.getImageData(0, 0, W, H).data;
  const out = new Float32Array(W * H);
  for (let i = 0; i < out.length; i++) out[i] = 0.299 * d[i * 4] + 0.587 * d[i * 4 + 1] + 0.114 * d[i * 4 + 2];
  let mean = 0;
  for (const v of out) mean += v;
  mean /= out.length;
  let sd = 0;
  for (const v of out) sd += (v - mean) ** 2;
  sd = Math.sqrt(sd / out.length) || 1;
  for (let i = 0; i < out.length; i++) out[i] = (out[i] - mean) / sd;
  return out;
}
const target = grey(picture, picture.naturalWidth * cx, picture.naturalHeight * cy, pw, ph);

const frames = (n: number) => new Promise<void>((done) => {
  let left = n;
  const tick = () => (--left <= 0 ? done() : requestAnimationFrame(tick));
  requestAnimationFrame(tick);
});

/** Correlation between the picture and the world seen from this camera. */
(window as unknown as { score: unknown }).score = async (fov: number, pitch: number, x = 0, y = 0, z = 0) => {
  camera.fov = fov;
  camera.rotation.x = THREE.MathUtils.degToRad(pitch);
  camera.position.set(x, y, z);
  camera.updateProjectionMatrix();
  for (let i = 0; i < 12; i++) {
    renderer.render(scene, camera);
    await frames(1);
  }
  const frame = grey(canvas, 0, 0, W, H);
  let s = 0;
  for (let i = 0; i < frame.length; i++) s += frame[i] * target[i];
  return s / frame.length;
};
(window as unknown as { ready: boolean }).ready = true;
