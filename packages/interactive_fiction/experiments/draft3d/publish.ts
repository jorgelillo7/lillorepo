/**
 * What the draft's Worker serves of its worlds, and how: each binary under a
 * name that carries a digest of its content, so it can be cached for good, and
 * the places of every hotspot and cut-out worked out at build, so the page
 * never downloads a collider mesh.
 */

import { createHash } from "node:crypto";

/** A hotspot's place in the room, or a corner of a cut-out: metres in the world's axes as the page draws them. */
export type Point = [x: number, y: number, z: number];

/** A world as `worlds.json` in the author's `web/3d/` describes it. */
export interface WorldSource {
  splats: string;
  collider: string;
  crop: [number, number];
  fovY: number;
  pitch: number;
  bounds?: [number, number];
  figures?: { image: string; rect: [number, number, number, number] }[];
  dolly?: number;
  camera?: Point;
  anchors?: Record<string, [number, number]>;
}

/** A world as the page receives it: the camera that reproduces the picture, and the splats under their hashed name. */
export interface ServedWorld {
  splats: string;
  crop: [number, number];
  fovY: number;
  pitch: number;
  bounds?: [number, number];
  dolly?: number;
  camera?: Point;
  /** Labels of the hotspots placed by hand: with any, a hotspot not listed stays a text choice. */
  placed?: string[];
}

/** One scene of one chapter, baked: where each of its hotspots is, and each cut-out's four corners (top-left, top-right, bottom-left, bottom-right). */
export interface BakedRoom {
  anchors: Record<string, Point>;
  figures: { image: string; corners: [Point, Point, Point, Point] }[];
}

/** `worlds.json` as served. `rooms` is keyed `chapter/scene`: one scene's hotspots differ between chapters. */
export interface Served {
  worlds: Record<string, ServedWorld>;
  rooms: Record<string, BakedRoom>;
}

/** `worlds/room-500k.spz` → `worlds/room-500k.1a2b3c4d5e.spz`: the name changes exactly when the content does. */
export function hashedName(path: string, bytes: Uint8Array): string {
  const digest = createHash("sha256").update(bytes).digest("hex").slice(0, 10);
  const dot = path.lastIndexOf(".");
  return dot > path.lastIndexOf("/") ? `${path.slice(0, dot)}.${digest}${path.slice(dot)}` : `${path}.${digest}`;
}

/** What the page needs of a world: everything but the collider, the cut-outs (baked per room) and the hand-placed fractions. */
export function servedWorld(world: WorldSource, splats: string): ServedWorld {
  return {
    splats,
    crop: world.crop,
    fovY: world.fovY,
    pitch: world.pitch,
    ...(world.bounds ? { bounds: world.bounds } : {}),
    ...(world.dolly !== undefined ? { dolly: world.dolly } : {}),
    ...(world.camera ? { camera: world.camera } : {}),
    ...(world.anchors ? { placed: Object.keys(world.anchors) } : {}),
  };
}

/** Fewer digits than a float prints: a tenth of a millimetre is far below what a hotspot's glow shows. */
export function rounded(p: { x: number; y: number; z: number }): Point {
  const r = (n: number) => Math.round(n * 1e4) / 1e4 || 0;
  return [r(p.x), r(p.y), r(p.z)];
}

/**
 * The `_headers` file of the draft's Worker: files under `worlds/` are named by their content and
 * never change, so a browser keeps them for a year without asking; everything else is checked
 * again on each visit (Cloudflare's default), so a new deploy shows at once. Every file gets a CSP
 * that forbids framing, plugins, `<base>` and form posts; script and style sources stay open until
 * the Spark renderer's needs (workers, WASM, blobs) are tested on Cloudflare.
 */
export function headersFile(): string {
  return [
    "# Written by prepare.ts. World files carry a digest of their content in their name.",
    "/worlds/*",
    "  Cache-Control: public, max-age=31536000, immutable",
    "/*",
    "  Content-Security-Policy: frame-ancestors 'none'; object-src 'none'; base-uri 'none'; form-action 'none'",
    "  Strict-Transport-Security: max-age=31536000",
    "  Permissions-Policy: camera=(), geolocation=(), microphone=(), payment=(), usb=()",
    "  X-Content-Type-Options: nosniff",
    "  X-Frame-Options: DENY",
    "  Referrer-Policy: same-origin",
    "",
  ].join("\n");
}
