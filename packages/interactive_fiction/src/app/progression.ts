/**
 * How a reader moves through a chapter, as pure functions on `Progress`: no
 * DOM, no storage. Advancing, undoing, restarting, whether a passage ends the
 * chapter, and the code carried in from the previous one.
 */

import type { Carry } from "../contract.ts";
import type { Action, Vars } from "../engine/runtime.ts";
import { toText } from "../engine/values.ts";

export interface Snapshot {
  passage: string;
  /** State *before* the passage rendered, so resuming never re-applies its (set:)s. */
  vars: Vars;
  /** The choice the reader made on this passage, once they left it. */
  choice?: string;
}

export interface Progress extends Snapshot {
  undo: Snapshot[];
  finished: boolean;
  /** The chapter's end code, once finished. */
  code?: string;
}

/** Undo steps kept; older ones are dropped. */
export const MAX_UNDO = 50;

export function freshStart(start: string, vars: Vars): Progress {
  return { passage: start, vars, undo: [], finished: false };
}

/**
 * Leave the current passage for `target`. `varsNow` is the state after the
 * current passage rendered (and any input typed or hook revealed on it).
 */
export function advance(p: Progress, target: string, varsNow: Vars, choice?: string): Progress {
  const step: Snapshot = { passage: p.passage, vars: p.vars, choice };
  return {
    passage: target,
    vars: structuredClone(varsNow),
    undo: [...p.undo, step].slice(-MAX_UNDO),
    finished: false,
  };
}

/** One step back, or null at the start. The step's choice is forgotten. */
export function undo(p: Progress): Progress | null {
  const prev = p.undo[p.undo.length - 1];
  if (!prev) return null;
  return { passage: prev.passage, vars: prev.vars, undo: p.undo.slice(0, -1), finished: false };
}

/** The choices that led here, in order. */
export function choicesOf(p: Progress): string[] {
  return p.undo.map((u) => u.choice).filter((c): c is string => Boolean(c));
}

/**
 * The previous chapter's code written into this chapter's code field while it
 * is still empty; anything else is left as it is.
 */
export function withCarriedCode(p: Progress, carry: Carry | null, previousCode: string | undefined): Progress {
  if (!carry || !previousCode || p.vars[carry.to] !== "") return p;
  return { ...p, vars: { ...p.vars, [carry.to]: previousCode } };
}

export interface Outcome {
  /** Nothing to click and nothing to type. */
  stuck: boolean;
  /** The chapter is over: stuck, and its end code (if it keeps one) is set. */
  ended: boolean;
  code?: string;
}

/**
 * A chapter that keeps an end code has ended only once the code is set; a
 * link-less passage before that is a path not written yet (drafts).
 */
export function outcomeOf(page: { actions: Action[]; inputs: string[] }, vars: Vars, carry: Carry | null): Outcome {
  const stuck = page.actions.length === 0 && page.inputs.length === 0;
  const raw = carry ? vars[carry.from] : undefined;
  const code = raw !== undefined ? toText(raw) : undefined;
  const ended = stuck && (code === undefined || code !== "");
  return { stuck, ended, code: ended && code ? code : undefined };
}

/** Mark the progress finished, once, with the code it ended on. */
export function finish(p: Progress, outcome: Outcome): Progress {
  if (!outcome.ended || p.finished) return p;
  return { ...p, finished: true, code: outcome.code };
}
