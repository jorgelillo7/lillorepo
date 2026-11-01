/**
 * What a chapter holds to discover (computed at build by exploring it) and
 * what a reader has found, without spoiling what they have not.
 */

import type { ExploreReport } from "./explore.ts";

export interface ChapterDiscoveries {
  /** "codes" when the chapter ends with a code, else the ending passages. */
  kind: "codes" | "passages";
  endings: string[];
  /** Passages a reader can land on. */
  passages: number;
}

export interface Found {
  endings: string[];
  passages: string[];
}

export function discoveriesOf(report: ExploreReport): ChapterDiscoveries {
  const codes = Object.keys(report.endCodes).sort();
  return codes.length
    ? { kind: "codes", endings: codes, passages: report.visited.length }
    : { kind: "passages", endings: Object.keys(report.deadEnds).sort(), passages: report.visited.length };
}

export interface Summary {
  /** Every ending in a stable order, the ones not found yet as null. */
  endings: (string | null)[];
  endingsFound: number;
  passagesSeen: number;
  passagesTotal: number;
}

export function summarize(all: ChapterDiscoveries, found: Found): Summary {
  const have = new Set(found.endings);
  const seen = new Set(found.passages);
  return {
    endings: all.endings.map((e) => (have.has(e) ? e : null)),
    endingsFound: all.endings.filter((e) => have.has(e)).length,
    passagesSeen: Math.min(seen.size, all.passages),
    passagesTotal: all.passages,
  };
}

export interface Achievement {
  id: string;
  title: string;
  done: boolean;
}

/** Generic achievements, derived only from what the engine knows. */
export function achievements(
  chapters: { id: string; title: string; discoveries: ChapterDiscoveries | null }[],
  found: Record<string, Found>,
  finished: Set<string>,
): Achievement[] {
  const out: Achievement[] = [];
  for (const c of chapters) {
    out.push({ id: `${c.id}:done`, title: `${c.title}: terminado`, done: finished.has(c.id) });
    if (!c.discoveries) continue;
    const s = summarize(c.discoveries, found[c.id] ?? { endings: [], passages: [] });
    if (c.discoveries.endings.length > 1) {
      out.push({ id: `${c.id}:endings`, title: `${c.title}: todos los finales`, done: s.endingsFound === c.discoveries.endings.length });
    }
    out.push({ id: `${c.id}:explored`, title: `${c.title}: todo explorado`, done: s.passagesSeen >= s.passagesTotal });
  }
  if (chapters.length > 1) {
    out.push({ id: "series:done", title: "Todos los capítulos", done: chapters.every((c) => finished.has(c.id)) });
  }
  return out;
}
