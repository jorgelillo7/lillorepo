/** Passage text → syntax tree, for the Harlowe markup the supported subset uses. */

import { parseArgs, type Expr } from "./expr.ts";
import { canonical, kindOf } from "./macros.ts";
import { StoryError } from "./values.ts";

export type Node =
  | { t: "text"; s: string }
  | { t: "br" }
  | { t: "link"; label: string; target: string }
  | { t: "macro"; name: string; args: Expr[]; hook?: Node[] }
  | { t: "hook"; body: Node[] }
  | { t: "collapsed"; body: Node[] }
  | { t: "style"; tag: "b" | "i"; body: Node[] }
  | { t: "html"; s: string }
  | { t: "var"; name: string; temp: boolean };

const MACRO_START = /^\(([A-Za-z][\w-]*):/;

/** Index of the `)` closing the macro whose `(` is at `i`. Strings and code hooks are skipped. */
function macroEnd(src: string, i: number): number {
  let parens = 0;
  let brackets = 0;
  for (let j = i; j < src.length; j++) {
    const c = src[j];
    if (brackets === 0 && (c === '"' || c === "'")) {
      const close = src.indexOf(c, j + 1);
      if (close === -1) throw new StoryError(`Unclosed string in macro: ${src.slice(i, i + 60)}`);
      j = close;
    } else if (c === "[") brackets++;
    else if (c === "]") brackets--;
    else if (brackets === 0 && c === "(") parens++;
    else if (brackets === 0 && c === ")") {
      parens--;
      if (parens === 0) return j;
    }
  }
  throw new StoryError(`Unclosed macro: ${src.slice(i, i + 60)}`);
}

export function parseLink(inner: string): { label: string; target: string } {
  const arrow = inner.lastIndexOf("->");
  if (arrow !== -1) return { label: inner.slice(0, arrow), target: inner.slice(arrow + 2) };
  const back = inner.indexOf("<-");
  if (back !== -1) return { label: inner.slice(back + 2), target: inner.slice(0, back) };
  const bar = inner.lastIndexOf("|");
  if (bar !== -1) return { label: inner.slice(0, bar), target: inner.slice(bar + 1) };
  return { label: inner, target: inner };
}

class MarkupParser {
  private pos = 0;
  private readonly src: string;

  constructor(src: string) {
    this.src = src;
  }

  private at(s: string): boolean {
    return this.src.startsWith(s, this.pos);
  }

  parse(stops: string[]): Node[] {
    const out: Node[] = [];
    let text = "";
    const flush = () => {
      if (text) out.push({ t: "text", s: text });
      text = "";
    };
    while (this.pos < this.src.length) {
      if (stops.some((s) => this.at(s))) break;
      const rest = this.src.slice(this.pos);
      if (this.at("[[")) {
        const end = this.src.indexOf("]]", this.pos + 2);
        if (end === -1) throw new StoryError(`Unclosed link: ${rest.slice(0, 60)}`);
        flush();
        out.push({ t: "link", ...parseLink(this.src.slice(this.pos + 2, end)) });
        this.pos = end + 2;
        continue;
      }
      const macro = MACRO_START.exec(rest);
      if (macro) {
        flush();
        out.push(this.macro(canonical(macro[1]), macro[0].length));
        continue;
      }
      if (this.at("{")) {
        flush();
        this.pos++;
        const body = this.parse(["}", ...stops]);
        if (!this.at("}")) throw new StoryError(`Unclosed { near: ${rest.slice(0, 60)}`);
        this.pos++;
        out.push({ t: "collapsed", body });
        continue;
      }
      if (this.at("[")) {
        const open = this.pos;
        this.pos++;
        const body = this.parse(["]", ...stops]);
        if (this.at("]")) {
          flush();
          this.pos++;
          out.push({ t: "hook", body });
          continue;
        }
        // No `]` closes it: the bracket is plain text.
        this.pos = open;
      }
      if (this.at("''") || this.at("//")) {
        const mark = this.at("''") ? "''" : "//";
        flush();
        this.pos += 2;
        const body = this.parse([mark, ...stops]);
        if (!this.at(mark)) throw new StoryError(`Unclosed ${mark} near: ${rest.slice(0, 60)}`);
        this.pos += 2;
        out.push({ t: "style", tag: mark === "''" ? "b" : "i", body });
        continue;
      }
      if (this.at("<!--")) {
        const end = this.src.indexOf("-->", this.pos);
        this.pos = end === -1 ? this.src.length : end + 3;
        continue;
      }
      const tag = /^<\/?[A-Za-z][^>]*>/.exec(rest);
      if (tag) {
        flush();
        out.push({ t: "html", s: tag[0] });
        this.pos += tag[0].length;
        continue;
      }
      const variable = /^\$([A-Za-z_]\w*)/.exec(rest);
      if (variable) {
        flush();
        out.push({ t: "var", name: variable[1], temp: false });
        this.pos += variable[0].length;
        continue;
      }
      const prev = this.pos > 0 ? this.src[this.pos - 1] : " ";
      const temp = /^_([A-Za-z]\w*)/.exec(rest);
      if (temp && !/\w/.test(prev)) {
        flush();
        out.push({ t: "var", name: temp[1], temp: true });
        this.pos += temp[0].length;
        continue;
      }
      if (this.at("\n")) {
        flush();
        out.push({ t: "br" });
        this.pos++;
        continue;
      }
      text += this.src[this.pos++];
    }
    flush();
    return out;
  }

  private macro(name: string, headLength: number): Node {
    const start = this.pos;
    const end = macroEnd(this.src, start);
    const argSrc = this.src.slice(start + headLength, end);
    // An unsupported macro may use syntax this parser does not know: leave its
    // arguments unparsed so the validator reports the macro itself.
    let args: Expr[] = [];
    if (kindOf(name)) {
      try {
        args = parseArgs(argSrc);
      } catch (e) {
        throw new StoryError(`(${name}:) ${(e as Error).message}`);
      }
    }
    this.pos = end + 1;
    if (kindOf(name) !== "changer") return { t: "macro", name, args };
    const ws = /^\s*/.exec(this.src.slice(this.pos))![0];
    const after = this.pos + ws.length;
    if (this.src[after] !== "[" || (this.src.startsWith("[[", after) && !this.src.startsWith("[[[", after))) {
      return { t: "macro", name, args };
    }
    this.pos = after + 1;
    const hook = this.parse(["]"]);
    if (!this.at("]")) throw new StoryError(`Unclosed hook of (${name}:)`);
    this.pos++;
    return { t: "macro", name, args, hook };
  }
}

export function parseMarkup(src: string): Node[] {
  const p = new MarkupParser(src);
  const nodes = p.parse([]);
  return nodes;
}
