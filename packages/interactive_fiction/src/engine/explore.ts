/** Plays every path through a chapter and reports what a reader can and cannot reach. */

import type { Carry } from "../contract.ts";
import { Runtime, type Action, type Vars } from "./runtime.ts";
import type { Story } from "./source.ts";
import { toText } from "./values.ts";

export interface ExploreOptions {
  /** Values tried for each variable bound to an `(input:)`. */
  inputs?: Record<string, string[]>;
  /** Variables set right after startup, as the reader does with a carried code. */
  preset?: Vars;
  /** Variable whose value at a dead end is the chapter's end code. */
  endVar?: string;
  /** Stop after this many distinct (passage, state) pairs. */
  maxStates?: number;
  /** Called with every distinct (passage, state) pair, before it is rendered. */
  onVisit?: (passage: string, vars: Vars) => void;
}

export interface ExploreReport {
  states: number;
  truncated: boolean;
  /** Passages reached, including those only shown through (display:). */
  reached: string[];
  /** Passages a reader lands on (not counting ones only displayed inside others). */
  visited: string[];
  unreached: string[];
  /** Passages with nothing to click, with how often they were reached. */
  deadEnds: Record<string, number>;
  /** End code → number of distinct end states producing it. */
  endCodes: Record<string, number>;
  /** End code → the shortest list of clicks (link labels, input values) that reaches it. */
  endPaths: Record<string, string[]>;
  /** Dead-end passage → the shortest list of clicks that reaches it. */
  deadEndPaths: Record<string, string[]>;
  /** Runtime errors, by passage. */
  errors: Record<string, string>;
}

function stable(vars: Vars): string {
  return JSON.stringify(Object.keys(vars).sort().map((k) => [k, vars[k]]));
}

function clone(vars: Vars): Vars {
  return structuredClone(vars);
}

/** Every combination of input values, as variable assignments. */
function inputCombos(names: string[], inputs: Record<string, string[]>): Vars[] {
  let combos: Vars[] = [{}];
  for (const name of [...new Set(names)]) {
    const values = inputs[name] ?? [""];
    combos = combos.flatMap((c) => values.map((v) => ({ ...c, [name]: v })));
  }
  return combos;
}

export function explore(story: Story, options: ExploreOptions = {}): ExploreReport {
  const rt = new Runtime(story);
  const displayed = new Set<string>();
  rt.onDisplay = (name) => displayed.add(name);
  const maxStates = options.maxStates ?? 200_000;
  const initial = { ...rt.start(), ...(options.preset ?? {}) };
  const seen = new Set<string>();
  const queue: { passage: string; vars: Vars; path: string[] }[] = [];
  const reached = new Set<string>();
  const deadEnds: Record<string, number> = {};
  const endCodes: Record<string, number> = {};
  const endPaths: Record<string, string[]> = {};
  const deadEndPaths: Record<string, string[]> = {};
  const errors: Record<string, string> = {};
  let truncated = false;

  const enqueue = (passage: string, vars: Vars, path: string[]) => {
    const key = passage + "\u0000" + stable(vars);
    if (seen.has(key)) return;
    if (seen.size >= maxStates) {
      truncated = true;
      return;
    }
    seen.add(key);
    queue.push({ passage, vars, path });
  };

  // Follow one action from a rendered page; a `(link:)` that reveals more links recurses.
  const follow = (vars: Vars, action: Action, path: string[]) => {
    const here = [...path, action.label];
    if (action.kind === "link") {
      enqueue(action.target, vars, here);
      return;
    }
    const out = rt.reveal(vars, action);
    if (out.goto) {
      enqueue(out.goto, vars, here);
      return;
    }
    if (out.actions.length === 0) return;
    for (let i = 0; i < out.actions.length; i++) {
      // Replay the reveal on a fresh copy so siblings do not share mutations.
      const branch = clone(vars);
      const again = rt.reveal(branch, action);
      follow(branch, again.actions[i], here);
    }
  };

  enqueue(story.start, initial, []);
  while (queue.length) {
    const { passage, vars, path } = queue.shift()!;
    options.onVisit?.(passage, clone(vars));
    try {
      const first = rt.visit(clone(vars), passage);
      reached.add(first.passage);
      if (first.actions.length === 0) {
        deadEnds[first.passage] = (deadEnds[first.passage] ?? 0) + 1;
        deadEndPaths[first.passage] ??= path;
        if (options.endVar) {
          const after = clone(vars);
          rt.visit(after, passage);
          const code = after[options.endVar];
          if (code !== undefined && toText(code) !== "") {
            const c = toText(code);
            endCodes[c] = (endCodes[c] ?? 0) + 1;
            // Breadth-first, so the first path to a code is a shortest one.
            endPaths[c] ??= path;
          }
        }
        continue;
      }
      for (const preset of inputCombos(first.inputs, options.inputs ?? {})) {
        for (let i = 0; i < first.actions.length; i++) {
          // Re-render on a fresh copy per action: rendering mutates state.
          const branch = clone(vars);
          const page = rt.visit(branch, passage);
          Object.assign(branch, preset);
          const typed = Object.values(preset).map((v) => `«${toText(v)}»`);
          follow(branch, page.actions[i], [...path, ...typed]);
        }
      }
    } catch (e) {
      errors[passage] = (e as Error).message;
    }
  }

  const all = story.passages
    .filter((p) => !p.tags.includes("startup") && !p.tags.includes("header"))
    .map((p) => p.name);
  const reachedAll = new Set([...reached, ...displayed]);
  return {
    states: seen.size,
    truncated,
    reached: [...reachedAll].sort(),
    visited: [...reached].sort(),
    unreached: all.filter((n) => !reachedAll.has(n)).sort(),
    deadEnds,
    endCodes,
    endPaths,
    deadEndPaths,
    errors,
  };
}

/** A code no chapter produces: how a chapter treats a wrong code is the baseline for an accepted one. */
export const WRONG_CODE = "NO-ES-UN-CODIGO";

/**
 * Explore a series' chapters in order. A chapter that asks for the previous
 * one's end code is tried with every code that chapter can produce, plus a
 * wrong one.
 */
export function exploreSeries(
  stories: Story[],
  carry: Carry | undefined,
  onVisit?: (chapter: number, passage: string, vars: Vars) => void,
): ExploreReport[] {
  const reports: ExploreReport[] = [];
  let previous: string[] = [];
  for (const [i, story] of stories.entries()) {
    const inputs = carry && previous.length ? { [carry.to]: [...previous, WRONG_CODE] } : {};
    const report = explore(story, { endVar: carry?.from, inputs, onVisit: onVisit && ((p, v) => onVisit(i, p, v)) });
    reports.push(report);
    previous = Object.keys(report.endCodes);
  }
  return reports;
}
