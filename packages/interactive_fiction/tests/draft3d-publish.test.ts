import { describe, expect, test } from "vitest";
import { hashedName, headersFile, rounded, servedWorld, type WorldSource } from "../experiments/draft3d/publish.ts";

const world: WorldSource = {
  splats: "worlds/room-500k.spz",
  collider: "worlds/room-collider.glb",
  crop: [0.03, 0.06],
  fovY: 47,
  pitch: -9,
  bounds: [-58, 72],
  figures: [{ image: "worlds/someone.png", rect: [10, 20, 30, 40] }],
  anchors: { Mirror: [0.5, 0.3], Door: [0.8, 0.5] },
};

describe("what the 3D draft serves of its worlds", () => {
  test("a world file is named by its content: the same bytes the same name, other bytes another", () => {
    const a = hashedName("worlds/room-500k.spz", new Uint8Array([1, 2, 3]));
    expect(a).toMatch(/^worlds\/room-500k\.[0-9a-f]{10}\.spz$/);
    expect(hashedName("worlds/room-500k.spz", new Uint8Array([1, 2, 3]))).toBe(a);
    expect(hashedName("worlds/room-500k.spz", new Uint8Array([1, 2, 4]))).not.toBe(a);
    expect(hashedName("worlds.v2/room", new Uint8Array([1]))).toMatch(/^worlds\.v2\/room\.[0-9a-f]{10}$/);
  });

  test("the page gets a world's camera and splats, never its collider, cut-out rectangles or hand-placed fractions", () => {
    const served = servedWorld(world, "worlds/room-500k.0123456789.spz");
    expect(served).toEqual({
      splats: "worlds/room-500k.0123456789.spz",
      crop: [0.03, 0.06],
      fovY: 47,
      pitch: -9,
      bounds: [-58, 72],
      placed: ["Mirror", "Door"],
    });
    expect(JSON.stringify(served)).not.toContain("collider");
    expect(servedWorld({ ...world, anchors: undefined, dolly: 0 }, "s").placed).toBeUndefined();
    expect(servedWorld({ ...world, dolly: 0 }, "s").dolly).toBe(0);
  });

  test("world files are cached for good and everything else is checked on each visit", () => {
    const lines = headersFile().split("\n");
    const at = lines.indexOf("/worlds/*");
    expect(lines[at + 1].trim()).toBe("Cache-Control: public, max-age=31536000, immutable");
    const rest = lines.slice(lines.indexOf("/*"));
    expect(rest.join("\n")).not.toContain("Cache-Control");
    expect(rest.map((l) => l.trim())).toContain("X-Content-Type-Options: nosniff");
  });

  test("every file forbids framing, plugins, <base> and form posts, and is HTTPS-only", () => {
    const rest = headersFile().split("\n").slice(headersFile().split("\n").indexOf("/*")).map((l) => l.trim());
    const csp = rest.find((l) => l.startsWith("Content-Security-Policy:"))!;
    for (const d of ["frame-ancestors 'none'", "object-src 'none'", "base-uri 'none'", "form-action 'none'"]) expect(csp).toContain(d);
    expect(rest).toContain("Strict-Transport-Security: max-age=31536000");
    expect(rest.some((l) => l.startsWith("Permissions-Policy:") && l.includes("camera=()"))).toBe(true);
  });

  test("a baked place keeps a tenth of a millimetre", () => {
    expect(rounded({ x: 1.234567, y: -0.00004, z: 2 })).toEqual([1.2346, 0, 2]);
  });
});
