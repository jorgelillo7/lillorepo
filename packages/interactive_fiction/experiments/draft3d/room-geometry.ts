/**
 * Where the things of a picture are in the world grown from it: the camera
 * that reproduces the picture, and rays cast from it onto the world's collider
 * mesh. Used at build (bake.ts), so the page gets places, not the mesh.
 */

import * as THREE from "three";
import { rounded, type BakedRoom, type Point, type WorldSource } from "./publish.ts";
import type { Scene } from "../../src/engine/scenes.ts";

/** Marble worlds use OpenCV axes (y down, z forward); three.js has y up, z back. */
export const OPENCV_TO_THREE = new THREE.Quaternion(1, 0, 0, 0);

/** Width over height of the trimmed picture the world was generated from. */
export function pictureAspect(aspect: [number, number], crop: [number, number]): number {
  return (aspect[0] * (1 - 2 * crop[0])) / (aspect[1] * (1 - 2 * crop[1]));
}

/** The picture's camera, as the world's starting view reproduces it. */
function pictureCamera(world: WorldSource, scene: Scene): THREE.PerspectiveCamera {
  const cam = new THREE.PerspectiveCamera(world.fovY, pictureAspect(scene.aspect, world.crop), 0.01, 200);
  cam.rotation.order = "YXZ";
  cam.rotation.x = THREE.MathUtils.degToRad(world.pitch);
  cam.position.fromArray(world.camera ?? [0, 0, 0]);
  cam.updateMatrixWorld(true);
  return cam;
}

/** A point of the picture (percent of the whole picture) as normalised device coordinates of the trimmed view. */
function ndc(world: WorldSource, xPct: number, yPct: number): THREE.Vector2 {
  const [cx, cy] = world.crop;
  const u = (xPct / 100 - cx) / (1 - 2 * cx);
  const v = (yPct / 100 - cy) / (1 - 2 * cy);
  return new THREE.Vector2(u * 2 - 1, 1 - v * 2);
}

/** Where a ray from the picture's camera lands on the collider; two metres out when it hits nothing. */
function cast(ray: THREE.Raycaster, cam: THREE.Camera, at: THREE.Vector2, collider: THREE.Object3D): THREE.Vector3 {
  ray.setFromCamera(at, cam);
  const hit = ray.intersectObject(collider, true)[0];
  return hit ? hit.point.clone() : ray.ray.at(2, new THREE.Vector3());
}

/**
 * Each hotspot's centre in the room. A world with hand-placed hotspots (`anchors`, fractions of its
 * own view) places only those.
 */
export function anchorsFor(world: WorldSource, scene: Scene, collider: THREE.Object3D): Record<string, Point> {
  const cam = pictureCamera(world, scene);
  const ray = new THREE.Raycaster();
  const anchors: Record<string, Point> = {};
  for (const spot of scene.hotspots) {
    const [x, y, w, h] = spot.rect;
    const placed = world.anchors?.[spot.label];
    if (world.anchors && !placed) continue;
    const at = placed ? new THREE.Vector2(placed[0] * 2 - 1, 1 - placed[1] * 2) : ndc(world, x + w / 2, y + h / 2);
    anchors[spot.label] = rounded(cast(ray, cam, at, collider));
  }
  return anchors;
}

/**
 * A cut-out's four corners: a quad facing the picture's camera at the depth of what lies under its
 * centre (the bed, for someone lying on it), sized so that from that camera it covers exactly its
 * rectangle of the picture.
 */
export function figureCorners(world: WorldSource, scene: Scene, collider: THREE.Object3D, rect: [number, number, number, number]): [Point, Point, Point, Point] {
  const cam = pictureCamera(world, scene);
  const [x, y, w, h] = rect;
  const centre = cast(new THREE.Raycaster(), cam, ndc(world, x + w / 2, y + h / 2), collider);
  const depth = centre.applyMatrix4(cam.matrixWorldInverse).z;
  const corner = (px: number, py: number): Point => {
    const p = ndc(world, px, py);
    const v = new THREE.Vector3(p.x, p.y, 0.5).unproject(cam).applyMatrix4(cam.matrixWorldInverse);
    return rounded(v.multiplyScalar(depth / v.z).applyMatrix4(cam.matrixWorld));
  };
  return [corner(x, y), corner(x + w, y), corner(x, y + h), corner(x + w, y + h)];
}

/** Everything the page needs to know about one scene of one chapter in its world. `image` is the cut-out's served name. */
export function bakeRoom(world: WorldSource, scene: Scene, collider: THREE.Object3D, image: (path: string) => string): BakedRoom {
  return {
    anchors: anchorsFor(world, scene, collider),
    figures: (world.figures ?? []).map((f) => ({ image: image(f.image), corners: figureCorners(world, scene, collider, f.rect) })),
  };
}
