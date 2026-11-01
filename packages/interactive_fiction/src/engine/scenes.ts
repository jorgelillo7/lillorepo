/** Point-and-click scenes: images with clickable areas, laid over a chapter's passages. */

import type { Action } from "./runtime.ts";
import type { Story } from "./source.ts";

export interface Hotspot {
  /** Shown on hover/focus and read by screen readers. */
  label: string;
  /** Passages this area leads to; the first one the passage currently offers wins. */
  targets: string[];
  /** `[x, y, width, height]` in percent of the image. */
  rect: [number, number, number, number];
}

export interface Scene {
  image: string;
  /**
   * The physical room this view belongs to. Moving between two different
   * rooms plays the door; two views of one room (a close-up, the same room
   * later) do not. A scene without a room never plays it.
   */
  room?: string;
  /** Width and height ratio of the image, e.g. `[16, 9]`. */
  aspect: [number, number];
  hotspots: Hotspot[];
}

export interface SceneFile {
  scenes: Record<string, Scene>;
  /** Passage name → scene id. Passages not listed are shown as text. */
  passages: Record<string, string>;
}

export interface ShownHotspot {
  hotspot: Hotspot;
  /** Index into the passage's actions. */
  action: number;
}

/**
 * Split a passage's actions into hotspots on the scene and the rest.
 * A hotspot appears only when one of its targets is a link the passage offers
 * right now, so the story's own conditions decide what can be clicked.
 */
export function hotspotsFor(scene: Scene, actions: Action[]): { shown: ShownHotspot[]; rest: number[] } {
  const used = new Set<number>();
  const shown: ShownHotspot[] = [];
  for (const hotspot of scene.hotspots) {
    for (const target of hotspot.targets) {
      const i = actions.findIndex((a, n) => !used.has(n) && a.kind === "link" && a.target === target);
      if (i !== -1) {
        used.add(i);
        shown.push({ hotspot, action: i });
        break;
      }
    }
  }
  const rest = actions.map((_, i) => i).filter((i) => !used.has(i));
  return { shown, rest };
}

/** Problems in a scene file, checked against the story it decorates. */
export function validateScenes(story: Story, file: SceneFile, imageExists: (path: string) => boolean): string[] {
  const names = new Set(story.passages.map((p) => p.name));
  const errors: string[] = [];
  for (const [id, scene] of Object.entries(file.scenes)) {
    if (!imageExists(scene.image)) errors.push(`Scene "${id}": image "${scene.image}" not found.`);
    for (const h of scene.hotspots) {
      for (const t of h.targets) {
        if (!names.has(t)) errors.push(`Scene "${id}": hotspot "${h.label}" targets "${t}", which is not a passage.`);
      }
    }
  }
  for (const [passage, sceneId] of Object.entries(file.passages)) {
    if (!names.has(passage)) errors.push(`Passage "${passage}" in the scene map does not exist.`);
    else if (!file.scenes[sceneId]) errors.push(`Passage "${passage}" uses scene "${sceneId}", which is not defined.`);
  }
  return errors;
}
