/** Reader preferences, in one localStorage key. Every access is guarded; defaults apply without storage. */

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

const KEY = "if:v1:settings";
const DEFAULTS: Settings = { volume: 0.5, muted: false, pacing: "paragraph", textSize: "m", effects: true };

let cached: Settings | null = null;

export function settings(): Settings {
  if (cached) return cached;
  try {
    const raw = localStorage.getItem(KEY);
    cached = { ...DEFAULTS, ...(raw ? (JSON.parse(raw) as Partial<Settings>) : {}) };
  } catch {
    cached = { ...DEFAULTS };
  }
  return cached;
}

export function updateSettings(change: Partial<Settings>): Settings {
  cached = { ...settings(), ...change };
  try {
    localStorage.setItem(KEY, JSON.stringify(cached));
  } catch {
    // Kept for this visit only.
  }
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
