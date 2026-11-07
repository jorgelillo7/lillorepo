/** Point-and-click scenes: images with clickable areas, laid over a chapter's passages. */

import type { Action } from "./runtime.ts";
import type { Story } from "./source.ts";

export interface Hotspot {
  /** Shown on hover/focus and read by screen readers. */
  label: string;
  /**
   * Passages this area leads to. One the passage offers is a straight click;
   * several offered at once — the exits of one door — open a menu of them.
   */
  targets: string[];
  /**
   * A scene id: tapping shows that scene for the same passage — stepping out
   * through a door — where the passage's choices sit on what they lead to.
   */
  view?: string;
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
  /**
   * Indexes into the passage's actions, in the hotspot's target order: one is
   * a click, more open a menu. For a view, the choices that view holds.
   */
  actions: number[];
  /** Set when tapping shows this scene instead of choosing. */
  view?: string;
}

/**
 * Split a passage's actions into hotspots on the scene and the rest.
 * A hotspot appears only when some of its targets are links the passage offers
 * right now, so the story's own conditions decide what can be clicked. A view
 * hotspot appears when the scene it shows (looked up in `scenes`, one level
 * deep) holds some of those choices.
 */
export function hotspotsFor(
  scene: Scene,
  actions: Action[],
  scenes: Record<string, Scene> = {},
): { shown: ShownHotspot[]; rest: number[] } {
  const used = new Set<number>();
  const shown: ShownHotspot[] = [];
  for (const hotspot of scene.hotspots) {
    if (hotspot.view) {
      const there = scenes[hotspot.view];
      const reached = there ? hotspotsFor(there, actions).shown.flatMap((h) => h.actions) : [];
      if (reached.length) shown.push({ hotspot, actions: reached, view: hotspot.view });
      continue;
    }
    const mine: number[] = [];
    for (const target of hotspot.targets) {
      const i = actions.findIndex((a, n) => !used.has(n) && a.kind === "link" && a.target === target);
      if (i === -1) continue;
      used.add(i);
      mine.push(i);
    }
    if (mine.length) shown.push({ hotspot, actions: mine });
  }
  const onScreen = new Set(shown.flatMap((h) => h.actions));
  const rest = actions.map((_, i) => i).filter((i) => !onScreen.has(i));
  return { shown, rest };
}

/** Problems in a scene file, checked against the story it decorates. */
export function validateScenes(story: Story, file: SceneFile, imageExists: (path: string) => boolean): string[] {
  const names = new Set(story.passages.map((p) => p.name));
  const errors: string[] = [];
  for (const [id, scene] of Object.entries(file.scenes)) {
    if (!imageExists(scene.image)) errors.push(`Scene "${id}": image "${scene.image}" not found.`);
    for (const h of scene.hotspots) {
      if (!(h.rect[2] > 0 && h.rect[3] > 0)) errors.push(`Scene "${id}": hotspot "${h.label}" has no area yet — place it on the image.`);
      if (h.view && !file.scenes[h.view]) errors.push(`Scene "${id}": hotspot "${h.label}" shows scene "${h.view}", which is not defined.`);
      if (!h.view && !h.targets.length) errors.push(`Scene "${id}": hotspot "${h.label}" leads nowhere: give it targets or a view.`);
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
