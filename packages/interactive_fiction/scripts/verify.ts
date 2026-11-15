/**
 * The one gate before anything ships: builds the site as it will be uploaded
 * (drafts left out; with STORIES_PUBLISH=1, only what the author published),
 * then explores every chapter strictly, compares every page with real Harlowe,
 * and plays the built site to every ending in a real browser. Stops at the
 * first step that fails, with its exit status; `dist/` is then what was checked.
 *
 *   npm run verify [-- --no-parity]
 *
 * `--no-parity` skips the Harlowe comparison and says so: for a place with no
 * Harlowe build to compare with (CI plays the fixture series). Never for a deploy.
 */

import { spawnSync } from "node:child_process";

const ROOT = new URL("../", import.meta.url).pathname;
const noParity = process.argv.includes("--no-parity");
if (noParity && process.env.STORIES_PUBLISH === "1") {
  console.error("✗ verify: --no-parity is not for a public deploy.");
  process.exit(1);
}

const steps: [name: string, command: string, args: string[]][] = [
  ["build", "npm", ["run", "build"]],
  ["explore --strict", "node", ["scripts/explore.ts", "--strict"]],
  ...(noParity ? [] : ([["parity", "node", ["scripts/parity.ts"]]] as [string, string, string[]][])),
  ["play to every ending", "node", ["scripts/play.ts"]],
];

for (const [name, command, args] of steps) {
  console.log(`\n── verify: ${name}`);
  const { status } = spawnSync(command, args, { cwd: ROOT, stdio: "inherit" });
  if (status !== 0) {
    console.error(`\n✗ verify stopped at "${name}": nothing ships until it passes.`);
    process.exit(status ?? 1);
  }
}
if (noParity) console.log("\n⚠ verify: the Harlowe comparison was SKIPPED (--no-parity).");
console.log(`\n✓ verify: ${steps.map(([name]) => name).join(", ")} passed.`);
