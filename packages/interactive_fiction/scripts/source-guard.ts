/**
 * What a public deploy may publish: a series' sources exactly as their repository's default
 * branch holds them on its origin. `npm run deploy` builds with STORIES_PUBLISH=1, and the build
 * then refuses a clone that is on another branch, has local changes or untracked files, or differs
 * from its origin after a fetch. STORIES_ALLOW_UNPUBLISHED=1 publishes anyway, for a deliberate
 * preview, and says so.
 */

import { execFileSync } from "node:child_process";
import { realpathSync } from "node:fs";

/** Runs git in `dir` and returns its trimmed output; throws if git fails. */
export type Git = (dir: string, args: string[]) => string;

export const realGit: Git = (dir, args) =>
  execFileSync("git", ["-C", dir, ...args], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();

/** The repository a folder belongs to (its top level), or null when it is not in one. */
export function repositoryOf(dir: string, git: Git = realGit): string | null {
  try {
    return git(realpathSync(dir), ["rev-parse", "--show-toplevel"]);
  } catch {
    return null;
  }
}

/**
 * Why `repo` must not be published, empty when it may: it is fetched first, then compared with
 * its origin's default branch.
 */
export function unpublishedReasons(repo: string, git: Git = realGit): string[] {
  try {
    git(repo, ["fetch", "--quiet", "origin"]);
  } catch (e) {
    return [`could not fetch its origin (${(e as Error).message.split("\n")[0]})`];
  }
  let remoteHead: string;
  try {
    remoteHead = git(repo, ["symbolic-ref", "--short", "refs/remotes/origin/HEAD"]);
  } catch {
    return ["its origin has no default branch recorded: run `git remote set-head origin --auto` in it"];
  }
  const defaultBranch = remoteHead.replace(/^origin\//, "");
  const reasons: string[] = [];
  const branch = git(repo, ["rev-parse", "--abbrev-ref", "HEAD"]);
  if (branch !== defaultBranch) reasons.push(`is on '${branch}', not '${defaultBranch}'`);
  const changes = git(repo, ["status", "--porcelain"]);
  if (changes) reasons.push(`has local changes or untracked files:\n${indent(changes)}`);
  const head = git(repo, ["rev-parse", "HEAD"]);
  const origin = git(repo, ["rev-parse", remoteHead]);
  if (head !== origin) reasons.push(`HEAD ${head.slice(0, 7)} differs from ${remoteHead} ${origin.slice(0, 7)}`);
  return reasons;
}

function indent(text: string): string {
  return text
    .split("\n")
    .map((line) => `      ${line}`)
    .join("\n");
}

/** Every reason, per series, its sources may not be published: one entry per repository behind it. */
export function publishProblems(
  series: { id: string; dir: string; sourceDir: string }[],
  git: Git = realGit,
): string[] {
  const problems: string[] = [];
  const checked = new Set<string>();
  for (const s of series) {
    for (const folder of new Set([s.dir, s.sourceDir])) {
      const repo = repositoryOf(folder, git);
      if (!repo) {
        problems.push(`${s.id}: ${folder} is not in a git repository, so nothing says which version it is`);
        continue;
      }
      if (checked.has(repo)) continue;
      checked.add(repo);
      for (const reason of unpublishedReasons(repo, git)) problems.push(`${s.id}: ${repo} ${reason}`);
    }
  }
  return problems;
}
