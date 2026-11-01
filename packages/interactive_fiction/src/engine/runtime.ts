/** Runs passages of a story against a state and renders them to HTML plus the actions they offer. */

import type { Expr } from "./expr.ts";
import { parseMarkup, parseLink, type Node } from "./markup.ts";
import type { Passage, Story } from "./source.ts";
import {
  COLOURS,
  StoryError,
  add,
  bool,
  equals,
  isHook,
  isIn,
  num,
  toText,
  type Value,
} from "./values.ts";

export type Vars = Record<string, Value>;

/** A clickable thing on the page. `link` navigates; `reveal` runs a `(link:)` hook in place. */
export type Action =
  | { kind: "link"; label: string; target: string }
  | { kind: "reveal"; label: string; body: Node[]; temps: Vars };

export interface Rendered {
  /** The passage actually shown, after any `(goto:)`. */
  passage: string;
  tags: string[];
  html: string;
  actions: Action[];
  /** Variables bound to `(input:)` fields, in page order. */
  inputs: string[];
}

export interface Revealed {
  html: string;
  actions: Action[];
  inputs: string[];
  /** Set when the hook navigated away. */
  goto?: string;
}

class Goto {
  readonly target: string;
  constructor(target: string) {
    this.target = target;
  }
}

const MAX_GOTOS = 100;

interface Ctx {
  vars: Vars;
  temps: Vars;
  actions: Action[];
  inputs: string[];
  collapse: boolean;
  depth: number;
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

export class Runtime {
  readonly story: Story;
  private readonly byName = new Map<string, Passage>();
  private readonly trees = new Map<string, Node[]>();
  /** Called with every passage shown through `(display:)`. */
  onDisplay?: (name: string) => void;

  constructor(story: Story) {
    this.story = story;
    for (const p of story.passages) this.byName.set(p.name, p);
  }

  passage(name: string): Passage {
    const p = this.byName.get(name);
    if (!p) throw new StoryError(`There is no passage named "${name}".`);
    return p;
  }

  has(name: string): boolean {
    return this.byName.has(name);
  }

  /** The parsed tree of a passage or code hook, cached by its source text. */
  tree(src: string): Node[] {
    let t = this.trees.get(src);
    if (!t) {
      t = parseMarkup(src);
      this.trees.set(src, t);
    }
    return t;
  }

  /** Fresh state: every `startup` passage run once, its output discarded. */
  start(): Vars {
    const vars: Vars = {};
    for (const p of this.story.passages.filter((x) => x.tags.includes("startup"))) {
      this.renderNodes(this.tree(p.text), this.ctx(vars));
    }
    return vars;
  }

  private ctx(vars: Vars, temps: Vars = {}): Ctx {
    return { vars, temps, actions: [], inputs: [], collapse: false, depth: 0 };
  }

  /** Show `name` with `vars` (mutated in place), following `(goto:)`s. */
  visit(vars: Vars, name: string): Rendered {
    let target = name;
    for (let hops = 0; hops < MAX_GOTOS; hops++) {
      const p = this.passage(target);
      const ctx = this.ctx(vars);
      try {
        const headers = this.story.passages
          .filter((x) => x.tags.includes("header"))
          .map((h) => this.renderNodes(this.tree(h.text), ctx))
          .join("");
        const body = this.renderNodes(this.tree(p.text), ctx);
        return { passage: target, tags: p.tags, html: headers + body, actions: ctx.actions, inputs: ctx.inputs };
      } catch (e) {
        if (e instanceof Goto) {
          target = e.target;
          continue;
        }
        throw e;
      }
    }
    throw new StoryError(`More than ${MAX_GOTOS} (goto:) in a row from "${name}".`);
  }

  /** Run a `(link:)` hook that was clicked. */
  reveal(vars: Vars, action: Extract<Action, { kind: "reveal" }>): Revealed {
    const ctx = this.ctx(vars, { ...action.temps });
    try {
      const html = this.renderNodes(action.body, ctx);
      return { html, actions: ctx.actions, inputs: ctx.inputs };
    } catch (e) {
      if (e instanceof Goto) return { html: "", actions: [], inputs: [], goto: e.target };
      throw e;
    }
  }

  // --- rendering -----------------------------------------------------------

  private renderNodes(nodes: Node[], ctx: Ctx): string {
    let out = "";
    // Outcome of the last if/unless/else-if among these siblings, for (else:).
    let last: boolean | undefined;
    for (const node of nodes) {
      if (node.t === "macro" && ["if", "unless", "else", "else-if"].includes(node.name)) {
        let show: boolean;
        if (node.name === "if" || node.name === "unless") {
          const v = bool(this.evalArg(node.args, 0, ctx), node.name);
          show = node.name === "if" ? v : !v;
          last = show;
        } else if (node.name === "else") {
          if (last === undefined) throw new StoryError("(else:) without an (if:) before it.");
          show = !last;
          last = true;
        } else {
          if (last === undefined) throw new StoryError("(else-if:) without an (if:) before it.");
          show = !last && bool(this.evalArg(node.args, 0, ctx), node.name);
          last = last || show;
        }
        if (!node.hook) throw new StoryError(`(${node.name}:) needs a hook [ ] after it.`);
        if (show) out += this.renderNodes(node.hook, ctx);
        continue;
      }
      out += this.renderNode(node, ctx);
    }
    return out;
  }

  private renderNode(node: Node, ctx: Ctx): string {
    switch (node.t) {
      case "text":
        return ctx.collapse ? node.s.replace(/\s+/g, " ") : node.s;
      case "br":
        return ctx.collapse ? " " : "<br>";
      case "html":
        return node.s;
      case "var": {
        const v = node.temp ? ctx.temps[node.name] : ctx.vars[node.name];
        if (v === undefined) throw new StoryError(`${node.temp ? "_" : "$"}${node.name} is not set.`);
        return escapeHtml(toText(v));
      }
      case "link":
        return this.linkHtml(ctx, { kind: "link", label: node.label, target: node.target });
      case "style":
        return `<${node.tag}>${this.renderNodes(node.body, ctx)}</${node.tag}>`;
      case "hook":
        return this.renderNodes(node.body, ctx);
      case "collapsed": {
        const inner = this.renderNodes(node.body, { ...ctx, collapse: true });
        return inner.replace(/ {2,}/g, " ").trim();
      }
      case "macro":
        return this.renderMacro(node, ctx);
    }
  }

  private linkHtml(ctx: Ctx, action: Action): string {
    const i = ctx.actions.push(action) - 1;
    return `<tw-link tabindex="0" role="link" data-action="${i}">${this.renderLabel(action.label)}</tw-link>`;
  }

  private renderLabel(label: string): string {
    return this.renderNodes(this.tree(label), this.ctx({}));
  }

  private renderMacro(node: Extract<Node, { t: "macro" }>, ctx: Ctx): string {
    switch (node.name) {
      case "set":
        for (const a of node.args) this.assign(a, ctx);
        return "";
      case "display": {
        const name = this.text(this.evalArg(node.args, 0, ctx), "display");
        if (ctx.depth > 50) throw new StoryError("(display:) nested too deep.");
        this.onDisplay?.(name);
        return this.renderNodes(this.tree(this.passage(name).text), { ...ctx, depth: ctx.depth + 1 });
      }
      case "goto":
        throw new Goto(this.text(this.evalArg(node.args, 0, ctx), "goto"));
      case "print":
        return this.renderValue(this.evalArg(node.args, 0, ctx), ctx);
      case "input": {
        const bind = node.args[0];
        if (!bind || bind.k !== "bind" || bind.target.k !== "var") {
          throw new StoryError("(input:) is supported only as (input: bind $variable).");
        }
        const name = bind.target.name;
        ctx.inputs.push(name);
        const current = ctx.vars[name];
        const value = typeof current === "string" ? escapeHtml(current) : "";
        return `<input class="tw-input" type="text" data-bind="${name}" value="${value}" autocomplete="off">`;
      }
      case "link": {
        const label = this.text(this.evalArg(node.args, 0, ctx), "link");
        if (!node.hook) throw new StoryError("(link:) needs a hook [ ] after it.");
        return this.linkHtml(ctx, { kind: "reveal", label, body: node.hook, temps: { ...ctx.temps } });
      }
      case "for": {
        const [lambda, ...rest] = node.args;
        if (!lambda || lambda.k !== "each") throw new StoryError("(for:) is supported as (for: each _x, ...).");
        if (!node.hook) throw new StoryError("(for:) needs a hook [ ] after it.");
        let out = "";
        for (const item of this.evalList(rest, ctx)) {
          out += this.renderNodes(node.hook, { ...ctx, temps: { ...ctx.temps, [lambda.temp]: item } });
        }
        return out;
      }
      case "text-colour": {
        const colour = this.colour(node.args[0], ctx);
        if (!node.hook) throw new StoryError(`(${node.name}:) needs a hook [ ] after it.`);
        return `<tw-hook style="color:${colour}">${this.renderNodes(node.hook, ctx)}</tw-hook>`;
      }
      default:
        return this.renderValue(this.evalCall(node.name, node.args, ctx), ctx);
    }
  }

  private renderValue(v: Value, ctx: Ctx): string {
    if (isHook(v)) return this.renderNodes(this.tree(v.src), ctx);
    if (typeof v === "string") return this.renderNodes(this.tree(v), ctx);
    return escapeHtml(toText(v));
  }

  private colour(arg: Expr | undefined, ctx: Ctx): string {
    if (!arg) throw new StoryError("(text-colour:) needs a colour.");
    if (arg.k === "ident") {
      const css = COLOURS[arg.name];
      if (!css) throw new StoryError(`Unknown colour "${arg.name}".`);
      return css;
    }
    const v = this.eval(arg, ctx);
    if (typeof v === "string" && /^#[0-9a-f]{3,8}$/i.test(v)) return v;
    if (typeof v === "string" && COLOURS[v.toLowerCase()]) return COLOURS[v.toLowerCase()];
    throw new StoryError(`Unknown colour ${JSON.stringify(v)}.`);
  }

  // --- evaluation ----------------------------------------------------------

  private assign(a: Expr, ctx: Ctx): void {
    if (a.k !== "assign") throw new StoryError("(set:) needs `$variable to value`.");
    const scope = a.target.k === "var" ? ctx.vars : ctx.temps;
    const name = (a.target as { name: string }).name;
    scope[name] = this.eval(a.e, ctx, scope[name]);
  }

  private evalArg(args: Expr[], i: number, ctx: Ctx): Value {
    const a = args[i];
    if (!a) throw new StoryError("Missing macro argument.");
    return this.eval(a, ctx);
  }

  private text(v: Value, macro: string): string {
    if (typeof v !== "string") throw new StoryError(`(${macro}:) needs a string.`);
    return v;
  }

  /** Arguments with `...spread` flattened. */
  private evalList(args: Expr[], ctx: Ctx): Value[] {
    const out: Value[] = [];
    for (const a of args) {
      if (a.k === "spread") {
        const v = this.eval(a.e, ctx);
        if (Array.isArray(v)) out.push(...v);
        else if (typeof v === "string") out.push(...v);
        else throw new StoryError("Only arrays and strings can be spread with ...");
      } else out.push(this.eval(a, ctx));
    }
    return out;
  }

  private eval(e: Expr, ctx: Ctx, it?: Value): Value {
    switch (e.k) {
      case "lit":
        return e.v;
      case "var": {
        const v = ctx.vars[e.name];
        if (v === undefined) throw new StoryError(`$${e.name} is not set.`);
        return v;
      }
      case "temp": {
        const v = ctx.temps[e.name];
        if (v === undefined) throw new StoryError(`_${e.name} is not set.`);
        return v;
      }
      case "it":
        if (it === undefined) throw new StoryError("`it` used where nothing is being set.");
        return it;
      case "hook":
        return { kind: "hook", src: e.src };
      case "ident":
        throw new StoryError(`Unknown word "${e.name}".`);
      case "not":
        return !bool(this.eval(e.e, ctx, it), "not");
      case "neg":
        return -num(this.eval(e.e, ctx, it), "-");
      case "call":
        return this.evalCall(e.name, e.args, ctx);
      case "bin":
        return this.binary(e, ctx, it);
      default:
        throw new StoryError(`Unexpected ${e.k} in an expression.`);
    }
  }

  private binary(e: Extract<Expr, { k: "bin" }>, ctx: Ctx, it?: Value): Value {
    if (e.op === "and") return bool(this.eval(e.l, ctx, it), "and") && bool(this.eval(e.r, ctx, it), "and");
    if (e.op === "or") return bool(this.eval(e.l, ctx, it), "or") || bool(this.eval(e.r, ctx, it), "or");
    const l = this.eval(e.l, ctx, it);
    const r = this.eval(e.r, ctx, it);
    switch (e.op) {
      case "is":
        return equals(l, r);
      case "is not":
        return !equals(l, r);
      case "is in":
        return isIn(l, r);
      case "contains":
        return isIn(r, l);
      case "<":
        return num(l, "<") < num(r, "<");
      case ">":
        return num(l, ">") > num(r, ">");
      case "<=":
        return num(l, "<=") <= num(r, "<=");
      case ">=":
        return num(l, ">=") >= num(r, ">=");
      case "+":
        return add(l, r);
      case "-":
        return num(l, "-") - num(r, "-");
      case "*":
        return num(l, "*") * num(r, "*");
      case "/":
        return num(l, "/") / num(r, "/");
    }
    throw new StoryError(`Unknown operator "${e.op}".`);
  }

  private evalCall(name: string, args: Expr[], ctx: Ctx): Value {
    switch (name) {
      case "a":
        return this.evalList(args, ctx);
      case "str":
        return this.evalList(args, ctx).map(toText).join("");
      case "uppercase":
        return this.text(this.evalArg(args, 0, ctx), name).toUpperCase();
      case "cond": {
        for (let i = 0; i + 1 < args.length; i += 2) {
          if (bool(this.eval(args[i], ctx), "cond")) return this.eval(args[i + 1], ctx);
        }
        if (args.length % 2 === 1) return this.eval(args[args.length - 1], ctx);
        throw new StoryError("(cond:) found no true condition and has no default.");
      }
      case "find": {
        const [lambda, ...rest] = args;
        if (!lambda || lambda.k !== "where") throw new StoryError("(find:) is supported as (find: _x where …, ...).");
        return this.evalList(rest, ctx).filter((item) =>
          bool(this.eval(lambda.cond, { ...ctx, temps: { ...ctx.temps, [lambda.temp]: item } }), "find"),
        );
      }
    }
    throw new StoryError(`(${name}:) is not supported.`);
  }
}

/** Every link target a passage could show, read from its source without running it. */
export function staticLinkTargets(text: string): string[] {
  const targets: string[] = [];
  for (const m of text.matchAll(/\[\[(.*?)\]\]/g)) targets.push(parseLink(m[1]).target);
  for (const m of text.matchAll(/\((?:goto|display):\s*"([^"]+)"\s*\)/g)) targets.push(m[1]);
  return targets;
}
