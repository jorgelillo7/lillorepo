/** Macro arguments: tokenizer and precedence parser for the supported Harlowe subset. */

import { canonical } from "./macros.ts";
import { StoryError } from "./values.ts";

export type Expr =
  | { k: "lit"; v: boolean | number | string }
  | { k: "var"; name: string }
  | { k: "temp"; name: string }
  | { k: "it" }
  | { k: "ident"; name: string }
  | { k: "hook"; src: string }
  | { k: "call"; name: string; args: Expr[] }
  | { k: "bin"; op: string; l: Expr; r: Expr }
  | { k: "prop"; obj: Expr; key: Expr }
  | { k: "not"; e: Expr }
  | { k: "neg"; e: Expr }
  | { k: "spread"; e: Expr }
  | { k: "assign"; target: Expr; e: Expr }
  | { k: "each"; temp: string }
  | { k: "where"; temp: string; cond: Expr }
  | { k: "bind"; target: Expr };

type Tok =
  | { t: "str"; v: string }
  | { t: "num"; v: number }
  | { t: "var"; v: string }
  | { t: "temp"; v: string }
  | { t: "word"; v: string; raw: string }
  | { t: "hook"; v: string }
  | { t: "op"; v: string };

const OPS = ["...", "<=", ">=", "(", ")", ",", ":", "<", ">", "+", "-", "*", "/"];

/** Whether the `'` at `i` is the `'s` of `$map's key` (right after a value, then a space), not a string. */
export function isPossessive(src: string, i: number): boolean {
  return src[i] === "'" && src[i + 1] === "s" && /[\w)]/.test(src[i - 1] ?? "") && /\s/.test(src[i + 2] ?? "");
}

/** The end of a `[...]` code hook starting at `i` (the index of `[`), bracket-balanced. */
export function hookEnd(src: string, i: number): number {
  let depth = 0;
  for (let j = i; j < src.length; j++) {
    if (src[j] === "[") depth++;
    else if (src[j] === "]") {
      depth--;
      if (depth === 0) return j;
    }
  }
  throw new StoryError("Unclosed [ in macro arguments.");
}

function tokenize(src: string): Tok[] {
  const toks: Tok[] = [];
  let i = 0;
  while (i < src.length) {
    const c = src[i];
    if (/\s/.test(c)) {
      i++;
      continue;
    }
    if (isPossessive(src, i)) {
      toks.push({ t: "op", v: "'s" });
      i += 2;
      continue;
    }
    if (c === '"' || c === "'") {
      let j = i + 1;
      let v = "";
      while (j < src.length && src[j] !== c) {
        if (src[j] === "\\" && j + 1 < src.length) {
          v += src[j + 1];
          j += 2;
        } else v += src[j++];
      }
      if (j >= src.length) throw new StoryError(`Unclosed string in: ${src}`);
      toks.push({ t: "str", v });
      i = j + 1;
      continue;
    }
    if (c === "[") {
      const end = hookEnd(src, i);
      toks.push({ t: "hook", v: src.slice(i + 1, end) });
      i = end + 1;
      continue;
    }
    let m = /^#[0-9a-fA-F]{3,8}\b/.exec(src.slice(i));
    if (m) {
      toks.push({ t: "str", v: m[0] });
      i += m[0].length;
      continue;
    }
    m = /^\d+(\.\d+)?/.exec(src.slice(i));
    if (m) {
      toks.push({ t: "num", v: Number(m[0]) });
      i += m[0].length;
      continue;
    }
    m = /^\$([A-Za-z_][\w]*)/.exec(src.slice(i));
    if (m) {
      toks.push({ t: "var", v: m[1] });
      i += m[0].length;
      continue;
    }
    m = /^_([A-Za-z][\w]*)/.exec(src.slice(i));
    if (m) {
      toks.push({ t: "temp", v: m[1] });
      i += m[0].length;
      continue;
    }
    m = /^[A-Za-z][\w-]*/.exec(src.slice(i));
    if (m) {
      toks.push({ t: "word", v: m[0].toLowerCase(), raw: m[0] });
      i += m[0].length;
      continue;
    }
    const op = OPS.find((o) => src.startsWith(o, i));
    if (!op) throw new StoryError(`Unexpected "${c}" in: ${src}`);
    toks.push({ t: "op", v: op });
    i += op.length;
  }
  return toks;
}

class Parser {
  private i = 0;
  private readonly toks: Tok[];
  private readonly src: string;

  constructor(src: string) {
    this.src = src;
    this.toks = tokenize(src);
  }

  private peek(o = 0): Tok | undefined {
    return this.toks[this.i + o];
  }

  private isOp(v: string, o = 0): boolean {
    const t = this.peek(o);
    return t?.t === "op" && t.v === v;
  }

  private isWord(v: string, o = 0): boolean {
    const t = this.peek(o);
    return t?.t === "word" && t.v === v;
  }

  private fail(msg: string): never {
    throw new StoryError(`${msg} in: ${this.src}`);
  }

  private expectOp(v: string): void {
    if (!this.isOp(v)) this.fail(`Expected "${v}"`);
    this.i++;
  }

  args(): Expr[] {
    const out: Expr[] = [];
    if (this.i >= this.toks.length || this.isOp(")")) return out;
    for (;;) {
      out.push(this.item());
      if (this.i >= this.toks.length || this.isOp(")")) break;
      this.expectOp(",");
    }
    return out;
  }

  private item(): Expr {
    if (this.isWord("each") && this.peek(1)?.t === "temp") {
      const temp = (this.peek(1) as { v: string }).v;
      this.i += 2;
      return { k: "each", temp };
    }
    if (this.peek()?.t === "temp" && this.isWord("where", 1)) {
      const temp = (this.peek() as { v: string }).v;
      this.i += 2;
      return { k: "where", temp, cond: this.or() };
    }
    if (this.isWord("bind")) {
      this.i++;
      return { k: "bind", target: this.primary() };
    }
    if (this.isOp("...")) {
      this.i++;
      return { k: "spread", e: this.or() };
    }
    const t = this.peek();
    if (t?.t === "var" || t?.t === "temp") {
      const start = this.i;
      const target = this.primary();
      if (this.isWord("to")) {
        this.i++;
        return { k: "assign", target, e: this.or() };
      }
      this.i = start;
    }
    return this.or();
  }

  private or(): Expr {
    let l = this.and();
    while (this.isWord("or")) {
      this.i++;
      l = { k: "bin", op: "or", l, r: this.and() };
    }
    return l;
  }

  private and(): Expr {
    let l = this.not();
    while (this.isWord("and")) {
      this.i++;
      l = { k: "bin", op: "and", l, r: this.not() };
    }
    return l;
  }

  private not(): Expr {
    if (this.isWord("not")) {
      this.i++;
      return { k: "not", e: this.not() };
    }
    return this.comparison();
  }

  private comparison(): Expr {
    let l = this.additive();
    for (;;) {
      let op: string | undefined;
      if (this.isWord("is") && this.isWord("not", 1)) op = "is not";
      else if (this.isWord("is") && this.isWord("in", 1)) op = "is in";
      else if (this.isWord("is")) op = "is";
      else if (this.isWord("contains")) op = "contains";
      else {
        const t = this.peek();
        if (t?.t === "op" && ["<", ">", "<=", ">="].includes(t.v)) op = t.v;
      }
      if (!op) return l;
      this.i += op.includes(" ") ? 2 : 1;
      l = { k: "bin", op, l, r: this.additive() };
    }
  }

  private additive(): Expr {
    let l = this.multiplicative();
    while (this.isOp("+") || this.isOp("-")) {
      const op = (this.peek() as { v: string }).v;
      this.i++;
      l = { k: "bin", op, l, r: this.multiplicative() };
    }
    return l;
  }

  private multiplicative(): Expr {
    let l = this.unary();
    while (this.isOp("*") || this.isOp("/")) {
      const op = (this.peek() as { v: string }).v;
      this.i++;
      l = { k: "bin", op, l, r: this.unary() };
    }
    return l;
  }

  private unary(): Expr {
    if (this.isOp("-")) {
      this.i++;
      return { k: "neg", e: this.unary() };
    }
    return this.primary();
  }

  /** An atom followed by any `'s key` / `'s (expression)` accesses. */
  private primary(): Expr {
    let e = this.atom();
    while (this.isOp("'s")) {
      this.i++;
      const t = this.peek();
      if (t?.t === "word") {
        this.i++;
        e = { k: "prop", obj: e, key: { k: "lit", v: t.raw } };
      } else if (this.isOp("(")) {
        e = { k: "prop", obj: e, key: this.atom() };
      } else this.fail("Expected a name or (expression) after 's");
    }
    return e;
  }

  private atom(): Expr {
    const t = this.peek();
    if (!t) this.fail("Unexpected end");
    if (t.t === "op" && t.v === "(") {
      const name = this.peek(1);
      if (name?.t === "word" && this.isOp(":", 2)) {
        this.i += 3;
        const args = this.args();
        this.expectOp(")");
        return { k: "call", name: canonical(name.v), args };
      }
      this.i++;
      const e = this.or();
      this.expectOp(")");
      return e;
    }
    this.i++;
    switch (t.t) {
      case "str":
        return { k: "lit", v: t.v };
      case "num":
        return { k: "lit", v: t.v };
      case "var":
        return { k: "var", name: t.v };
      case "temp":
        return { k: "temp", name: t.v };
      case "hook":
        return { k: "hook", src: t.v };
      case "word":
        if (t.v === "true") return { k: "lit", v: true };
        if (t.v === "false") return { k: "lit", v: false };
        if (t.v === "it") return { k: "it" };
        return { k: "ident", name: t.v };
    }
    this.fail(`Unexpected "${t.v}"`);
  }

  done(): void {
    if (this.i < this.toks.length) this.fail("Unexpected trailing input");
  }
}

/** Parse the text between `(name:` and `)` into argument expressions. */
export function parseArgs(src: string): Expr[] {
  const p = new Parser(src);
  const args = p.args();
  p.done();
  return args;
}
