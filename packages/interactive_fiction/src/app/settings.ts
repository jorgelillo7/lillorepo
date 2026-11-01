/** Reader preferences, in one storage key; defaults apply without storage. */

import { readJson, writeJson } from "./storage.ts";

export interface Settings {
  /** 0–1. */
  volume: number;
  muted: boolean;
  /** How a passage's text appears. */
  pacing: "all" | "paragraph";
  textSize: "s" | "m" | "l";
  /** Shakes, flickers and distortions. Also off whenever the system asks for reduced motion. */
  effects: boolean;
}

const KEY = "settings";
const DEFAULTS: Settings = { volume: 0.5, muted: false, pacing: "paragraph", textSize: "m", effects: true };

let cached: Settings | null = null;

export function settings(): Settings {
  cached ??= { ...DEFAULTS, ...readJson<Partial<Settings>>(KEY, {}) };
  return cached;
}

export function updateSettings(change: Partial<Settings>): Settings {
  cached = { ...settings(), ...change };
  writeJson(KEY, cached);
  applySettings();
  return cached;
}

/** Settings that live in CSS. */
export function applySettings(): void {
  const s = settings();
  const root = document.documentElement;
  root.dataset.textSize = s.textSize;
  root.dataset.effects = s.effects ? "on" : "off";
}
