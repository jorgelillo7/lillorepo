/**
 * Plays every path of every chapter and prints a report for the author:
 * unreachable passages, dead ends, end codes, runtime errors, and whether each
 * end code of a chapter is accepted by the next one.
 *
 *   node scripts/explore.ts [series] [--strict]
 *
 * With `--strict` it exits non-zero when a published chapter has something to fix before it ships
 * (`shipProblems`, or a code of the previous chapter it rejects), or when there is no chapter to
 * check at all. A draft is reported and never fails: it is unfinished by definition.
 */

import { exploreSeries, rejectedCodes, shipProblems } from "../src/engine/explore.ts";
import { loadSeries, seriesIds } from "./series.ts";

function section(title: string, lines: string[]): void {
  if (lines.length) console.log(`  ${title}:\n${lines.map((l) => `    - ${l}`).join("\n")}`);
}

const args = process.argv.slice(2);
const strict = args.includes("--strict");
const only = args.find((a) => !a.startsWith("--"));
const failures: string[] = [];
let checked = 0;

for (const id of only ? [only] : seriesIds()) {
  const series = loadSeries(id);
  const carry = series.manifest.carry;
  console.log(`\n# ${series.manifest.title}`);
  const reports = exploreSeries(series.stories, carry);
  series.manifest.chapters.forEach((entry, i) => {
    const story = series.stories[i];
    const report = reports[i];
    const previous = i > 0 ? Object.keys(reports[i - 1].endCodes) : [];
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

    const rejected = carry && previous.length ? rejectedCodes(story, carry, previous) : [];
    if (!entry.draft) {
      checked++;
      const problems = [...shipProblems(report), ...rejected.map((code) => `code ${code} from the previous chapter is treated like a wrong code`)];
      failures.push(...problems.map((p) => `${id}/${entry.id}: ${p}`));
    }
    if (carry && previous.length) {
      section(
        `Codes from chapter ${series.manifest.chapters[i - 1].id} treated like a wrong code`,
        rejected,
      );
      if (!rejected.length) console.log(`  Every code from chapter ${series.manifest.chapters[i - 1].id} is accepted.`);
    }
  });
}

if (strict) {
  if (!checked) failures.push("no published chapter to check");
  for (const f of failures) console.log(`✗ ${f}`);
  if (failures.length) {
    console.error(`\n${failures.length} thing(s) to fix before shipping.`);
    process.exit(1);
  }
  console.log(`\n✓ ${checked} published chapter(s): nothing to fix before shipping.`);
}
