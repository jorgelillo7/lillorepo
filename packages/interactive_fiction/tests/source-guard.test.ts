import { execFileSync } from "node:child_process";
import { mkdirSync, mkdtempSync, realpathSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { beforeEach, describe, expect, it } from "vitest";
import { publishProblems, unpublishedReasons } from "../scripts/source-guard.ts";

const git = (dir: string, ...args: string[]) =>
  execFileSync("git", ["-C", dir, ...args], {
    encoding: "utf8",
    env: { ...process.env, GIT_AUTHOR_NAME: "t", GIT_AUTHOR_EMAIL: "t@t", GIT_COMMITTER_NAME: "t", GIT_COMMITTER_EMAIL: "t@t" },
  }).trim();

/** An author's clone as `npm run deploy` finds it: master, clean, equal to its origin. */
function authorClone(): { clone: string; origin: string } {
  const root = realpathSync(mkdtempSync(join(tmpdir(), "if-guard-")));
  const origin = join(root, "origin.git");
  execFileSync("git", ["init", "--quiet", "--bare", "--initial-branch=master", origin]);
  const clone = join(root, "clone");
  execFileSync("git", ["clone", "--quiet", origin, clone], { stdio: "ignore" });
  mkdirSync(join(clone, "web"));
  writeFileSync(join(clone, "web", "series.json"), "{}");
  git(clone, "add", ".");
  git(clone, "commit", "--quiet", "-m", "chapter 1");
  git(clone, "push", "--quiet", "origin", "HEAD:master");
  git(clone, "remote", "set-head", "origin", "master");
  return { clone, origin };
}

describe("what a public deploy may publish", () => {
  let clone: string;

  beforeEach(() => {
    ({ clone } = authorClone());
  });

  it("publishes the default branch, clean and equal to its origin", () => {
    expect(unpublishedReasons(clone)).toEqual([]);
    expect(publishProblems([{ id: "s", dir: join(clone, "web"), sourceDir: clone }])).toEqual([]);
  });

  it("refuses another branch", () => {
    git(clone, "checkout", "--quiet", "-b", "web-3d");
    expect(unpublishedReasons(clone).join()).toContain("is on 'web-3d', not 'master'");
  });

  it("refuses local changes and untracked files", () => {
    writeFileSync(join(clone, "web", "series.json"), '{"draft": true}');
    writeFileSync(join(clone, "web", "new-scene.json"), "{}");
    const reasons = unpublishedReasons(clone).join();
    expect(reasons).toContain("has local changes or untracked files");
    expect(reasons).toContain("new-scene.json");
  });

  it("refuses a local commit its origin does not have", () => {
    writeFileSync(join(clone, "web", "series.json"), '{"v": 2}');
    git(clone, "commit", "--quiet", "-am", "not pushed");
    expect(unpublishedReasons(clone).join()).toContain("differs from origin/master");
  });

  it("refuses a clone behind its origin, which the fetch reveals", () => {
    const other = join(clone, "..", "other");
    execFileSync("git", ["clone", "--quiet", join(clone, "..", "origin.git"), other], { stdio: "ignore" });
    writeFileSync(join(other, "web", "series.json"), '{"v": 3}');
    git(other, "commit", "--quiet", "-am", "the author's next chapter");
    git(other, "push", "--quiet", "origin", "HEAD:master");
    expect(unpublishedReasons(clone).join()).toContain("differs from origin/master");
  });

  it("refuses a series folder outside any repository", () => {
    const loose = realpathSync(mkdtempSync(join(tmpdir(), "if-loose-")));
    expect(publishProblems([{ id: "s", dir: loose, sourceDir: loose }]).join()).toContain("not in a git repository");
  });

  it("checks a repository once when the series and its sources share it", () => {
    git(clone, "checkout", "--quiet", "-b", "web-3d");
    const problems = publishProblems([{ id: "s", dir: join(clone, "web"), sourceDir: clone }]);
    expect(problems).toHaveLength(1);
  });
});
