/**
 * Paragraph-by-paragraph reveal of a rendered passage. Only the passage's
 * top-level nodes are grouped, at line breaks; an element is never split, so
 * the author's own HTML (a diary page, his HUD, an input) always appears
 * whole. Nothing is removed: every node is moved, in order, into a segment,
 * and every segment is eventually shown.
 */

import { reducedMotion } from "./dom.ts";

const isBr = (n: Node) => n.nodeType === Node.ELEMENT_NODE && (n as Element).tagName === "BR";
const isBlank = (n: Node) => n.nodeType === Node.TEXT_NODE && !n.textContent!.trim();

/** Shorter paragraphs are joined with the next, so the reader is not asked to tap after every line. */
const MIN_CHARS = 300;

/**
 * Group the passage's children into `<tw-seg>` blocks at line breaks, joining
 * short ones up to MIN_CHARS; returns the segments. The breaks stay inside the
 * segments, so the text lays out exactly as before.
 */
export function segment(passage: HTMLElement): HTMLElement[] {
  const nodes = [...passage.childNodes];
  const lines: Node[][] = [[]];
  for (let i = 0; i < nodes.length; i++) {
    lines[lines.length - 1].push(nodes[i]);
    if (isBr(nodes[i])) {
      // Keep a whole run of breaks (a blank line) with the line it ends.
      let j = i + 1;
      while (j < nodes.length && (isBr(nodes[j]) || isBlank(nodes[j]))) lines[lines.length - 1].push(nodes[j++]);
      i = j - 1;
      lines.push([]);
    }
  }
  const text = (group: Node[]) => group.map((n) => n.textContent ?? "").join("").trim();
  const groups: Node[][] = [];
  for (const line of lines) {
    if (!line.length) continue;
    const last = groups[groups.length - 1];
    if (last && (text(last).length < MIN_CHARS || !text(line))) last.push(...line);
    else groups.push([...line]);
  }
  // A short tail is joined to the paragraph before it.
  if (groups.length > 1 && text(groups[groups.length - 1]).length < MIN_CHARS / 3) {
    const tail = groups.pop()!;
    groups[groups.length - 1].push(...tail);
  }
  return groups.map((group) => {
    const seg = document.createElement("tw-seg");
    for (const n of group) seg.appendChild(n);
    passage.appendChild(seg);
    return seg;
  });
}

export interface Pacing {
  /** Show the next paragraph; true when that was the last one. */
  next(): boolean;
  all(): void;
  done(): boolean;
}

/**
 * Hide every paragraph but the first; `onDone` runs once everything is shown
 * (right away when `instant`, or when there is a single paragraph).
 */
export function pace(passage: HTMLElement, instant: boolean, onDone: () => void): Pacing {
  const segments = segment(passage);
  let shown = instant ? segments.length : Math.min(1, segments.length);
  segments.forEach((s, i) => (s.hidden = i >= shown));
  let finished = false;
  const finish = () => {
    if (finished) return;
    finished = true;
    onDone();
  };
  const pacing: Pacing = {
    next() {
      if (shown >= segments.length) {
        finish();
        return true;
      }
      const seg = segments[shown++];
      seg.hidden = false;
      seg.classList.add("seg-in");
      seg.scrollIntoView({ block: "nearest", behavior: reducedMotion() ? "auto" : "smooth" });
      if (shown >= segments.length) finish();
      return shown >= segments.length;
    },
    all() {
      for (const s of segments) s.hidden = false;
      shown = segments.length;
      finish();
    },
    done: () => finished,
  };
  if (shown >= segments.length) finish();
  return pacing;
}
