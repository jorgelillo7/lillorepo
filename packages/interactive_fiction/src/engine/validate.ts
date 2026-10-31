/** Static checks run before a story is built: anything the reader cannot run fails loudly here. */

import type { Expr } from "./expr.ts";
import { CHANGERS, SUPPORTED, parseMarkup, type Node } from "./markup.ts";
import type { Story } from "./source.ts";

export interface Issue {
  level: "error" | "warning";
  passage: string;
  message: string;
}

interface Scan {
  passage: string;
  issues: Issue[];
  read: Map<string, string>;
  set: Set<string>;
  targets: { target: string; passage: string }[];
}

function walkExpr(e: Expr, scan: Scan): void {
  switch (e.k) {
    case "var":
      if (!scan.read.has(e.name)) scan.read.set(e.name, scan.passage);
      return;
    case "lit":
      // Strings holding markup are printed with (print:), so their links count.
      if (typeof e.v === "string" && /\[\[|\([A-Za-z][\w-]*:/.test(e.v)) walkSource(e.v, scan);
      return;
    case "hook":
      walkSource(e.src, scan);
      return;
    case "call":
      if (!SUPPORTED.has(e.name)) issue(scan, "error", `(${e.name}:) is not supported.`);
      e.args.forEach((a) => walkExpr(a, scan));
      return;
    case "bin":
      walkExpr(e.l, scan);
      walkExpr(e.r, scan);
      return;
    case "not":
    case "neg":
    case "spread":
      walkExpr(e.e, scan);
      return;
    case "assign":
      if (e.target.k === "var") scan.set.add(e.target.name);
      walkExpr(e.e, scan);
      return;
    case "where":
      walkExpr(e.cond, scan);
      return;
    case "bind":
      if (e.target.k === "var") scan.set.add(e.target.name);
      return;
    default:
      return;
  }
}

function issue(scan: Scan, level: Issue["level"], message: string): void {
  scan.issues.push({ level, passage: scan.passage, message });
}

function walkNodes(nodes: Node[], scan: Scan): void {
  for (const n of nodes) {
    switch (n.t) {
      case "link":
        scan.targets.push({ target: n.target, passage: scan.passage });
        break;
      case "var":
        if (!n.temp && !scan.read.has(n.name)) scan.read.set(n.name, scan.passage);
        break;
      case "macro": {
        if (!SUPPORTED.has(n.name)) issue(scan, "error", `(${n.name}:) is not supported.`);
        if (CHANGERS.has(n.name) && !n.hook) issue(scan, "error", `(${n.name}:) has no hook [ ] after it.`);
        if (n.name === "goto" || n.name === "display") {
          const a = n.args[0];
          if (a?.k === "lit" && typeof a.v === "string") scan.targets.push({ target: a.v, passage: scan.passage });
          else if (n.name === "goto") issue(scan, "warning", "(goto:) target is computed; not checked.");
        }
        n.args.forEach((a) => walkExpr(a, scan));
        if (n.hook) walkNodes(n.hook, scan);
        break;
      }
      case "hook":
      case "collapsed":
      case "style":
        walkNodes(n.body, scan);
        break;
    }
  }
}

function walkSource(src: string, scan: Scan): void {
  try {
    walkNodes(parseMarkup(src), scan);
  } catch (e) {
    issue(scan, "error", (e as Error).message);
  }
}

/** Every problem found in `story`, errors first. */
export function validate(story: Story): Issue[] {
  const names = new Set(story.passages.map((p) => p.name));
  const scan: Scan = { passage: "", issues: [], read: new Map(), set: new Set(), targets: [] };
  if (!names.has(story.start)) {
    scan.issues.push({ level: "error", passage: "", message: `Start passage "${story.start}" does not exist.` });
  }
  if (!story.passages.some((p) => p.tags.includes("startup"))) {
    scan.issues.push({ level: "warning", passage: "", message: "No startup passage: variables start unset." });
  }
  for (const p of story.passages) {
    scan.passage = p.name;
    walkSource(p.text, scan);
  }
  for (const { target, passage } of scan.targets) {
    if (!names.has(target)) {
      scan.issues.push({ level: "error", passage, message: `Links to "${target}", which does not exist.` });
    }
  }
  for (const [name, passage] of scan.read) {
    if (!scan.set.has(name)) {
      scan.issues.push({ level: "error", passage, message: `$${name} is read but never set.` });
    }
  }
  for (const name of scan.set) {
    if (!scan.read.has(name)) {
      scan.issues.push({ level: "warning", passage: "", message: `$${name} is set but never read.` });
    }
  }
  return scan.issues.sort((a, b) => (a.level === b.level ? 0 : a.level === "error" ? -1 : 1));
}
