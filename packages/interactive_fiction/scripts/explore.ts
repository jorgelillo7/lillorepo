/**
 * Plays every path of every chapter and prints a report for the author:
 * unreachable passages, dead ends, end codes, runtime errors, and whether each
 * end code of a chapter is accepted by the next one.
 *
 *   node scripts/explore.ts [series]
 */

import { explore, type ExploreReport } from "../src/engine/explore.ts";
import { loadSeries, seriesIds } from "./series.ts";

const WRONG_CODE = "NO-ES-UN-CODIGO";

function section(title: string, lines: string[]): void {
  if (lines.length) console.log(`  ${title}:\n${lines.map((l) => `    - ${l}`).join("\n")}`);
}

for (const id of process.argv[2] ? [process.argv[2]] : seriesIds()) {
  const series = loadSeries(id);
  const carry = series.manifest.carry;
  console.log(`\n# ${series.manifest.title}`);
  let previous: string[] = [];
  series.manifest.chapters.forEach((entry, i) => {
    const story = series.stories[i];
    const inputs = carry && previous.length ? { [carry.to]: [...previous, WRONG_CODE] } : {};
    const report: ExploreReport = explore(story, { endVar: carry?.from, inputs });
    console.log(`\n## ${entry.id} · ${story.title}${entry.draft ? " (draft)" : ""}`);
    console.log(`  ${report.states} states explored${report.truncated ? " — TRUNCATED, results incomplete" : ""}`);
    section("Unreachable passages", report.unreached);
    section(
      "Dead ends (nothing to click)",
      Object.entries(report.deadEnds).map(([p, n]) => `${p} (${n} ways in)`),
    );
    section(
      "End codes, with the shortest way to each",
      Object.entries(report.endCodes).map(
        ([c, n]) => `${c} (${n} ways): ${(report.endPaths[c] ?? []).join(" → ")}`,
      ),
    );
    section(
      "Runtime errors",
      Object.entries(report.errors).map(([p, m]) => `${p}: ${m}`),
    );

    if (carry && previous.length) {
      // A code the chapter accepts lets the reader reach more than a wrong code does.
      const reach = (code: string) =>
        explore(story, { endVar: carry.from, inputs: { [carry.to]: [code] } }).reached.length;
      const wrong = reach(WRONG_CODE);
      const rejected = previous.filter((code) => reach(code) <= wrong);
      section(
        `Codes from chapter ${series.manifest.chapters[i - 1].id} treated like a wrong code`,
        rejected,
      );
      if (!rejected.length) console.log(`  Every code from chapter ${series.manifest.chapters[i - 1].id} is accepted.`);
    }
    previous = Object.keys(report.endCodes);
  });
}
