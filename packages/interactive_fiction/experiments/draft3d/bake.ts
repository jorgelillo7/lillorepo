/**
 * Bakes the draft's rooms at build: reads each world's collider mesh from disk,
 * casts the hotspots and cut-outs of every chapter's scenes onto it, and
 * returns their places. The mesh itself (1–10 MB a room) is never served.
 */

import { readFileSync } from "node:fs";
import type * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import type { ChapterData } from "../../src/contract.ts";
import type { BakedRoom, WorldSource } from "./publish.ts";
import { bakeRoom, OPENCV_TO_THREE } from "./room-geometry.ts";

const colliders = new Map<string, Promise<THREE.Object3D>>();

/** A collider mesh, parsed once per file and turned into the page's axes. */
function loadCollider(file: string): Promise<THREE.Object3D> {
  let p = colliders.get(file);
  if (!p) {
    const bytes = readFileSync(file);
    p = new GLTFLoader().parseAsync(bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer, "").then((gltf) => {
      gltf.scene.quaternion.copy(OPENCV_TO_THREE);
      gltf.scene.updateMatrixWorld(true);
      return gltf.scene;
    });
    colliders.set(file, p);
  }
  return p;
}

/**
 * The baked rooms of every chapter, keyed `chapter/scene`, for the scenes that have a world.
 * `file` resolves a path of worlds.json on disk; `image` gives a cut-out's served name.
 */
export async function bakeRooms(
  chapters: { id: string; data: ChapterData }[],
  worlds: Record<string, WorldSource>,
  file: (path: string) => string,
  image: (path: string) => string,
): Promise<Record<string, BakedRoom>> {
  const rooms: Record<string, BakedRoom> = {};
  for (const { id, data } of chapters) {
    for (const [sceneId, scene] of Object.entries(data.scenes?.scenes ?? {})) {
      const world = worlds[sceneId];
      if (!world) continue;
      rooms[`${id}/${sceneId}`] = bakeRoom(world, scene, await loadCollider(file(world.collider)), image);
    }
  }
  return rooms;
}
