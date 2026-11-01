/**
 * The game layer a series can add over its chapters: sound, documents, the
 * condition and inventory read from the story's own variables, and the title
 * screen. Everything here is configuration in the series folder; the story
 * text is never changed.
 */

import type { Story } from "./source.ts";
import { toText, type Value } from "./values.ts";

/** Sounds the reader synthesizes; no audio files, so no licences to track. */
export const AMBIENCES = ["hum", "drip", "drone", "wind", "silence"] as const;
export type Ambience = (typeof AMBIENCES)[number];

export interface PassageRef {
  chapter: string;
  passage: string;
}

export interface QuoteRef extends PassageRef {
  /** A sentence copied from the passage. */
  text: string;
}

export interface ConditionState {
  value: number;
  /** The author's own word for it, as his story prints it. */
  label: string;
  level: "fine" | "caution" | "danger" | "critical";
}

export interface GameConfig {
  title?: {
    /** An image under the series folder, already registered in the art bible. */
    image?: string;
    tagline?: string;
    /** Content warning shown before playing. */
    warning?: string;
  };
  audio?: {
    /** Ambience when nothing more specific applies. */
    default?: Ambience;
    /** Scene room → ambience. */
    rooms?: Record<string, Ambience>;
    /** Passage tag → ambience, for passages shown without a scene. */
    tags?: Record<string, Ambience>;
    /** Passages that open with a scare sting. */
    stings?: PassageRef[];
  };
  /** Passages shown as a document (a diary page, a file) over the scene. */
  documents?: (PassageRef & { title: string })[];
  condition?: {
    /** Story variable holding it, e.g. a sanity number. */
    variable: string;
    states: ConditionState[];
    /** A selector for the author's own HUD, hidden only when named here. */
    hideAuthorHud?: string;
  };
  inventory?: {
    /** Story variable holding an array of item names. */
    variable: string;
    /** Item name → what "examine" shows: a sentence quoted from the text. */
    items?: Record<string, { quote: QuoteRef }>;
  };
}

/** The state whose value matches; unknown values get none. */
export function conditionFor(config: GameConfig, value: Value | undefined): ConditionState | undefined {
  if (!config.condition || typeof value !== "number") return undefined;
  return config.condition.states.find((s) => s.value === value);
}

/** The inventory as item names, or nothing when the chapter does not track one. */
export function inventoryOf(config: GameConfig, vars: Record<string, Value>): string[] | undefined {
  const v = config.inventory ? vars[config.inventory.variable] : undefined;
  return Array.isArray(v) ? v.map(toText) : undefined;
}

/** The ambience for what is on screen: the scene's room, then the passage's tags, then the default. */
export function ambienceFor(config: GameConfig, room: string | undefined, tags: string[]): Ambience {
  const audio = config.audio ?? {};
  if (room && audio.rooms?.[room]) return audio.rooms[room];
  for (const tag of tags) if (audio.tags?.[tag]) return audio.tags[tag];
  return audio.default ?? "silence";
}

export function isSting(config: GameConfig, chapter: string, passage: string): boolean {
  return Boolean(config.audio?.stings?.some((s) => s.chapter === chapter && s.passage === passage));
}

export function documentFor(config: GameConfig, chapter: string, passage: string): { title: string } | undefined {
  return config.documents?.find((d) => d.chapter === chapter && d.passage === passage);
}

const squash = (s: string) =>
  s
    .replace(/\/\/|''/g, "")
    .replace(/\s+/g, " ")
    .trim();

/**
 * Problems in a game config, against the series' chapters. `variablesSet` is
 * every story variable some chapter assigns, so a HUD bound to a misspelt
 * variable fails here rather than showing nothing.
 */
export function validateGame(
  config: GameConfig,
  chapters: Record<string, Story>,
  variablesSet: Set<string>,
  fileExists: (path: string) => boolean,
): string[] {
  const errors: string[] = [];
  const passage = (ref: PassageRef) => chapters[ref.chapter]?.passages.find((p) => p.name === ref.passage);
  const checkRef = (what: string, ref: PassageRef) => {
    if (!passage(ref)) errors.push(`${what}: passage "${ref.passage}" not found in chapter ${ref.chapter}.`);
  };
  if (config.title?.image && !fileExists(config.title.image)) {
    errors.push(`title: image "${config.title.image}" not found.`);
  }
  const audio = config.audio ?? {};
  const ambiences = [audio.default, ...Object.values(audio.rooms ?? {}), ...Object.values(audio.tags ?? {})];
  for (const a of ambiences) {
    if (a !== undefined && !(AMBIENCES as readonly string[]).includes(a)) errors.push(`audio: unknown ambience "${a}".`);
  }
  for (const s of audio.stings ?? []) checkRef("audio sting", s);
  for (const d of config.documents ?? []) checkRef(`document "${d.title}"`, d);
  if (config.condition && !variablesSet.has(config.condition.variable)) {
    errors.push(`condition: no chapter sets $${config.condition.variable}.`);
  }
  if (config.inventory) {
    if (!variablesSet.has(config.inventory.variable)) errors.push(`inventory: no chapter sets $${config.inventory.variable}.`);
    for (const [name, item] of Object.entries(config.inventory.items ?? {})) {
      const p = passage(item.quote);
      if (!p) errors.push(`inventory item "${name}": passage "${item.quote.passage}" not found.`);
      else if (!squash(p.text).includes(squash(item.quote.text))) {
        errors.push(`inventory item "${name}": the quote is no longer in "${item.quote.passage}".`);
      }
    }
  }
  return errors;
}
